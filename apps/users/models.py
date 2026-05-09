import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator, MinLengthValidator
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone

from .utils import validate_birthday_not_future


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def _encrypt_secret(value: str) -> str:
    if not value:
        return value
    try:
        _fernet().decrypt(value.encode())
        return value  # already encrypted
    except (InvalidToken, Exception):
        return _fernet().encrypt(value.encode()).decode()


def _decrypt_secret(value: str) -> str:
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value  # graceful fallback for legacy plaintext values


class EncryptedCharField(models.CharField):
    """CharField that transparently encrypts on write and decrypts on read."""

    def from_db_value(self, value, expression, connection):
        return _decrypt_secret(value)

    def get_prep_value(self, value):
        return _encrypt_secret(super().get_prep_value(value))

    def to_python(self, value):
        return _decrypt_secret(value) if value else value


class AuthUserManager(BaseUserManager):
    """
    Custom manager for AuthUser where username is the primary identifier.
    """
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("The Username field must be set")
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)


class AuthUser(AbstractUser):
    objects = AuthUserManager()

    username = models.CharField(
        max_length=150,
        unique=True,
        null=False,
        blank=False,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9._-]+$",
                message="Username can only contain letters, numbers, dots, underscores, and hyphens.",
            ),
            MinLengthValidator(3, message="Username must be at least 3 characters long."),
        ],
    )

    full_name = models.CharField(
        max_length=255,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-ZÀ-ÿ'\- ]+$",
                message="Only letters, hyphens, apostrophes, and spaces are allowed.",
            ),
            MinLengthValidator(2, message="Full name must be at least 2 characters long."),
        ],
    )

    email = models.EmailField(
        unique=True,
        max_length=254,
        null=False,
        blank=False,
        help_text="Primary email address for the user.",
    )

    email_verified = models.BooleanField(
        default=False,
        help_text="Indicates whether the user's email has been verified.",
    )

    profile_picture = models.ImageField(
        upload_to="profile_pics/",
        null=True,
        blank=True,
        help_text="User's profile picture (auto-cropped to 1:1).",
    )

    # ── Two-Factor Authentication ────────────────────────────────────────────
    totp_secret = EncryptedCharField(max_length=256, blank=True, default="")
    totp_enabled = models.BooleanField(default=False)

    birthday = models.DateField(
        null=True,
        blank=True,
        validators=[validate_birthday_not_future],
        help_text="User's date of birth.",
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        managed = True
        db_table = "auth_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        
        super().save(*args, **kwargs)

        # Image processing: Square cropping (1:1)
        if self.profile_picture:
            from PIL import Image
            import os

            img_path = self.profile_picture.path
            if os.path.exists(img_path):
                img = Image.open(img_path)
                
                # If image is not square, crop it
                width, height = img.size
                if width != height:
                    min_dim = min(width, height)
                    left = (width - min_dim) / 2
                    top = (height - min_dim) / 2
                    right = (width + min_dim) / 2
                    bottom = (height + min_dim) / 2
                    
                    img = img.crop((left, top, right, bottom))
                    
                    # Resize to a reasonable standard (e.g. 512x512)
                    img.thumbnail((512, 512), Image.LANCZOS)
                    img.save(img_path)

    @property
    def display_name(self):
        """Returns the user's preferred display name."""
        return self.full_name or self.username


class EmailVerificationOTP(models.Model):
    """
    Single-use 6-digit OTP for email-based registration verification.
    Created when a user registers; deleted once they successfully verify.
    OneToOne ensures at most one pending OTP per user — a resend simply
    overwrites the existing record via update_or_create.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_otp",
    )
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "email_verification_otp"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.user.email} (expires {self.expires_at})"


class UserSession(models.Model):
    """
    Tracks active JWT refresh token sessions per user.
    One record per login; updated on every token refresh.
    Revoking a session blacklists the corresponding refresh token.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_sessions",
    )
    jti = models.CharField(
        max_length=255,
        unique=True,
        help_text="JWT ID of the current refresh token for this session.",
    )
    device = models.CharField(max_length=200, blank=True)
    browser = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "user_session"
        ordering = ["-last_active"]

    def __str__(self):
        return f"{self.user} — {self.browser} ({self.ip_address})"
