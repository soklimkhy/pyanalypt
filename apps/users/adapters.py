"""
Custom adapter for django-allauth to handle Google OAuth signin
and populate AuthUser model fields with Google metadata
"""

import logging
from urllib.parse import urlparse

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from .utils import sanitize_username

_ALLOWED_PICTURE_HOSTS = {
    "googleusercontent.com",
    "lh1.googleusercontent.com",
    "lh2.googleusercontent.com",
    "lh3.googleusercontent.com",
    "lh4.googleusercontent.com",
    "lh5.googleusercontent.com",
    "lh6.googleusercontent.com",
    "googleapis.com",
}

User = get_user_model()
logger = logging.getLogger(__name__)


def _generate_unique_username(email):
    """
    Derive a unique username from the local part of an email address.
    Appends an incrementing counter if the base username is already taken.
    Uses IntegrityError handling to be safe under concurrent signups.
    """
    email_prefix = sanitize_username(email.split("@")[0])
    username = email_prefix
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{email_prefix}{counter}"
        counter += 1
    return username


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom Social Account Adapter to populate AuthUser fields
    from Google OAuth metadata automatically.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a social provider,
        but before the login is actually processed.

        This is where we connect existing users if their email matches.
        """
        if sociallogin.is_existing:
            return

        if sociallogin.account.provider == "google":
            email = sociallogin.account.extra_data.get("email")
            if email:
                try:
                    user = User.objects.get(email=email)
                    sociallogin.connect(request, user)
                except User.DoesNotExist:
                    pass

    def populate_user(self, request, sociallogin, data):
        """
        Populate user information from social provider data (Google).
        This is called when creating a NEW user via social login.
        """
        user = super().populate_user(request, sociallogin, data)

        if sociallogin.account.provider == "google":
            extra_data = sociallogin.account.extra_data
            self._extract_google_names(user, extra_data)
            self._extract_google_picture(user, extra_data)
            self._verify_google_email(user, extra_data)

            if not user.username:
                user.username = _generate_unique_username(user.email)

        return user

    def _extract_google_names(self, user, extra_data):
        full_name = extra_data.get("name", "")
        if not full_name:
            given = extra_data.get("given_name", "") or extra_data.get("first_name", "")
            family = extra_data.get("family_name", "") or extra_data.get("last_name", "")
            if given and family:
                full_name = f"{given} {family}"
            elif given or family:
                full_name = given or family
        user.full_name = full_name

    def _extract_google_picture(self, user, extra_data):
        picture_url = extra_data.get("picture", "")
        if not picture_url:
            return

        parsed = urlparse(picture_url)
        host = parsed.netloc.lower()
        allowed = any(
            host == h or host.endswith(f".{h}") for h in _ALLOWED_PICTURE_HOSTS
        )
        if parsed.scheme != "https" or not allowed:
            logger.warning("Blocked profile picture download from untrusted host: %s", host)
            return

        import requests
        from django.core.files.base import ContentFile

        try:
            response = requests.get(picture_url, timeout=10)
            if response.status_code == 200:
                filename = f"google_avatar_{user.email.split('@')[0]}.jpg"
                user.profile_picture.save(filename, ContentFile(response.content), save=False)
        except Exception as e:
            logger.error("Failed to download Google profile picture for %s: %s", user.email, e)

    def _verify_google_email(self, user, extra_data):
        if extra_data.get("verified_email", False) or extra_data.get(
            "email_verified", False
        ):
            user.email_verified = True

    def save_user(self, request, sociallogin, form=None):
        """
        Save a newly created user via social login.
        """
        for attempt in range(3):
            try:
                user = super().save_user(request, sociallogin, form)
                break
            except IntegrityError:
                if attempt == 2:
                    raise
                # Username collision under concurrent signup — retry with a new one
                sociallogin.user.username = _generate_unique_username(
                    sociallogin.user.email
                )

        if sociallogin.account.provider == "google":
            from allauth.account.models import EmailAddress

            EmailAddress.objects.filter(user=user, email=user.email).update(
                verified=True
            )

        return user


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom Account Adapter for regular (non-social) signups.
    """

    def get_email_confirmation_url(self, request, emailconfirmation):
        """
        Build the link that goes inside the verification email.
        Points to the frontend page which then POSTs the key to
        POST /api/v1/auth/registration/verify-email/
        """
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        url_template = getattr(settings, "ACCOUNT_EMAIL_CONFIRMATION_URL", None)
        if not url_template:
            if not settings.DEBUG:
                raise ImproperlyConfigured(
                    "ACCOUNT_EMAIL_CONFIRMATION_URL must be set in production settings."
                )
            url_template = "http://localhost:3000/verify-email/{key}"

        return url_template.format(key=emailconfirmation.key)

    def save_user(self, request, user, form, commit=True):
        """
        Save user from signup form.
        """
        user = super().save_user(request, user, form, commit=False)

        cleaned = form.cleaned_data if hasattr(form, "cleaned_data") else {}
        if not user.full_name:
            user.full_name = cleaned.get("full_name", "")

        if user.email:
            user.email = user.email.lower()

        if not user.username and user.email:
            user.username = _generate_unique_username(user.email)

        if commit:
            for attempt in range(3):
                try:
                    user.save()
                    break
                except IntegrityError:
                    if attempt == 2:
                        raise
                    # Username collision under concurrent signup — retry with a new one
                    user.username = _generate_unique_username(user.email)

        return user
