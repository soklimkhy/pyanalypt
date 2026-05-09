import logging
import pyotp
import random
import user_agents
import uuid

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from dj_rest_auth.views import LoginView, PasswordChangeView

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

from .models import UserSession, EmailVerificationOTP
from .serializers import (
    CustomUserDetailsSerializer,
    InitialRegisterSerializer,
    RegistrationOTPVerifySerializer,
    CompleteProfileSerializer,
    ResendOTPSerializer,
    UserSessionSerializer,
    TOTPEnableSerializer,
    TOTPDisableSerializer,
    TOTPVerifyLoginSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _parse_user_agent(request):
    ua_str = request.META.get("HTTP_USER_AGENT", "")
    ua = user_agents.parse(ua_str)
    device = ua.device.family if ua.device.family != "Other" else "Desktop"
    browser = ua.browser.family
    if ua.os.family and ua.os.family != "Other":
        browser = f"{browser} on {ua.os.family}"
    return device, browser


def _create_session(request, user, refresh_token_str):
    """Create a UserSession record for a newly issued refresh token.
    Returns the created UserSession, or None if session tracking fails."""
    try:
        jti = JWTRefreshToken(refresh_token_str)["jti"]
    except Exception:
        logger.exception("Failed to extract JTI for session tracking (user=%s)", user.pk)
        return None  # Never block login due to session-tracking failure

    device, browser = _parse_user_agent(request)
    return UserSession.objects.create(
        user=user,
        jti=jti,
        device=device,
        browser=browser,
        ip_address=_get_client_ip(request),
    )


def _revoke_session(session):
    """Blacklist the token and mark the session inactive."""
    try:
        outstanding = OutstandingToken.objects.get(jti=session.jti)
        BlacklistedToken.objects.get_or_create(token=outstanding)
    except OutstandingToken.DoesNotExist:
        pass  # Token already expired and removed from outstanding table
    session.is_active = False
    session.save(update_fields=["is_active"])


# ── Throttles ─────────────────────────────────────────────────────────────────

class RegistrationThrottle(AnonRateThrottle):
    scope = "registration"

class OtpVerifyThrottle(AnonRateThrottle):
    scope = "otp_verify"

class OtpResendThrottle(AnonRateThrottle):
    scope = "otp_resend"

class LoginThrottle(AnonRateThrottle):
    scope = "login"

class TOTPVerifyThrottle(AnonRateThrottle):
    scope = "totp_verify"

class TOTPActionThrottle(UserRateThrottle):
    scope = "totp_action"

class PasswordChangeThrottle(UserRateThrottle):
    scope = "password_change"


# ── Registration ─────────────────────────────────────────────────────────────

class CustomRegisterView(APIView):
    """
    POST /auth/registration/
    Step 1: Validates email and password, creates an inactive user with a
    temporary username, and sends a 6-digit OTP.
    """

    permission_classes = [AllowAny]
    throttle_classes = [RegistrationThrottle]

    def post(self, request):
        serializer = InitialRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            # Create user with a temporary username based on a UUID fragment
            temp_username = f"user_{uuid.uuid4().hex[:10]}"
            user = User.objects.create_user(
                username=temp_username,
                email=data["email"],
                password=data["password"],
                is_active=False,
            )
        except IntegrityError:
            return Response(
                {"detail": "A user with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_code = f"{random.SystemRandom().randint(0, 999999):06d}"
        EmailVerificationOTP.objects.update_or_create(
            user=user,
            defaults={
                "otp": otp_code,
                "expires_at": timezone.now() + timedelta(minutes=10),
            },
        )

        try:
            send_mail(
                subject="Your PyAnalypt verification code",
                message=(
                    f"Hello,\n\n"
                    f"Your verification code is: {otp_code}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"Please use this code to verify your email and continue your registration."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send OTP email to %s", user.email)

        return Response(
            {"detail": "Initial registration successful. Please check your email for the 6-digit verification code."},
            status=status.HTTP_201_CREATED,
        )


class RegistrationOTPVerifyView(APIView):
    """
    POST /auth/registration/verify-otp/
    Step 2: Verifies the OTP, activates the user, and returns JWT tokens.
    User is now 'authenticated' but may still need to complete their profile.
    """

    permission_classes = [AllowAny]
    throttle_classes = [OtpVerifyThrottle]

    def post(self, request):
        serializer = RegistrationOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp_code = serializer.validated_data["otp"]

        _invalid = Response(
            {"detail": "Invalid email or OTP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return _invalid

        if user.email_verified:
            return Response(
                {"detail": "This email is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            otp_record = EmailVerificationOTP.objects.get(user=user)
        except EmailVerificationOTP.DoesNotExist:
            return _invalid

        if otp_record.is_expired():
            otp_record.delete()
            return Response(
                {"detail": "OTP has expired. Please request a new code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_record.otp != otp_code:
            return _invalid

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=["is_active", "email_verified"])
        otp_record.delete()

        refresh = JWTRefreshToken.for_user(user)
        refresh_str = str(refresh)
        session = _create_session(request, user, refresh_str)

        access_token = refresh.access_token
        if session:
            access_token["session_id"] = session.pk

        return Response({
            "access": str(access_token),
            "refresh": refresh_str,
            "requires_profile_completion": True,
            "user": CustomUserDetailsSerializer(user, context={"request": request}).data,
        })


class ResendOTPView(APIView):
    """
    POST /auth/registration/resend-otp/
    Regenerates and resends the verification OTP for a pending user.
    """

    permission_classes = [AllowAny]
    throttle_classes = [OtpResendThrottle]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Silent failure or generic success message to prevent enumeration
            return Response({"detail": "If an account exists with this email, a new code has been sent."})

        if user.email_verified:
            # Return the same generic message to avoid confirming which accounts are verified.
            return Response({"detail": "If an account exists with this email, a new code has been sent."})

        otp_code = f"{random.SystemRandom().randint(0, 999999):06d}"
        EmailVerificationOTP.objects.update_or_create(
            user=user,
            defaults={
                "otp": otp_code,
                "expires_at": timezone.now() + timedelta(minutes=10),
            },
        )

        try:
            send_mail(
                subject="Your PyAnalypt verification code",
                message=f"Your new verification code is: {otp_code}\n\nExpires in 10 minutes.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to resend OTP email to %s", user.email)

        return Response({"detail": "A new verification code has been sent to your email."})


class CompleteProfileView(APIView):
    """
    POST /auth/registration/complete-profile/
    Step 3: Finalizes the registration by setting username, full_name, and birthday.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.full_name and user.birthday:
            return Response(
                {"detail": "Profile has already been completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CompleteProfileSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user.username = data["username"]
        user.full_name = data["full_name"]
        user.birthday = data["birthday"]
        user.save(update_fields=["username", "full_name", "birthday"])

        return Response({
            "detail": "Profile completed successfully.",
            "user": CustomUserDetailsSerializer(user, context={"request": request}).data,
        })


# ── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleLogin(SocialLoginView):
    """
    Google OAuth2 login endpoint for frontend applications.

    Frontend should:
    1. Use Google Sign-In to get access_token
    2. Send access_token to this endpoint
    3. Receive JWT tokens back (or a totp_token if the account has 2FA enabled)
    """

    adapter_class = GoogleOAuth2Adapter
    callback_url = getattr(settings, "GOOGLE_OAUTH_CALLBACK_URL", None)
    client_class = OAuth2Client

    def get_response(self):
        # 1. 2FA Gate
        if self.user.totp_enabled:
            totp_token = signing.dumps(
                {"uid": self.user.pk, "purpose": "2fa-login"},
                salt="2fa-login",
            )
            return Response(
                {"requires_2fa": True, "totp_token": totp_token},
                status=status.HTTP_202_ACCEPTED,
            )

        session = _create_session(self.request, self.user, str(self.refresh_token))
        if session:
            self.access_token["session_id"] = session.pk

        # 2. Check Profile Completion Status
        is_profile_complete = bool(self.user.full_name and self.user.birthday)
        response = super().get_response()
        if not is_profile_complete:
            response.data["requires_profile_completion"] = True

        return response


# ── Custom login (adds 2FA gate + session tracking) ───────────────────────────

class CustomLoginView(LoginView):
    """
    Overrides dj-rest-auth LoginView to:
    - Intercept login when 2FA is enabled and return a short-lived totp_token
      instead of JWT tokens (frontend must complete via /auth/2fa/verify-login/).
    - Create a UserSession record on every successful full login.
    """

    throttle_classes = [LoginThrottle]

    def post(self, request):
        self.request = request

        # Pre-check: Detect unverified accounts before Django's auth backend rejects them
        # (which it does for is_active=False users). This ensures the frontend
        # receives a 'requires_verification' signal instead of a generic login error.
        email = request.data.get("email", "").strip().lower()
        if email:
            user_found = User.objects.filter(email__iexact=email).first()
            if user_found and not user_found.email_verified:
                return Response(
                    {
                        "detail": "Email address not verified.",
                        "requires_verification": True,
                        "email": user_found.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        self.serializer = self.get_serializer(data=request.data)
        self.serializer.is_valid(raise_exception=True)

        user = self.serializer.validated_data["user"]

        # 1. Check Email Verification Status
        if not user.email_verified:
            return Response(
                {
                    "detail": "Email address not verified.",
                    "requires_verification": True,
                    "email": user.email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Check 2FA Gate
        if user.totp_enabled:
            totp_token = signing.dumps(
                {"uid": user.pk, "purpose": "2fa-login"},
                salt="2fa-login",
            )
            return Response(
                {"requires_2fa": True, "totp_token": totp_token},
                status=status.HTTP_202_ACCEPTED,
            )

        self.login()
        session = _create_session(request, user, str(self.refresh_token))
        if session:
            self.access_token["session_id"] = session.pk

        # 3. Check Profile Completion Status
        is_profile_complete = bool(user.full_name and user.birthday)
        
        response = self.get_response()
        if not is_profile_complete:
            response.data["requires_profile_completion"] = True
            
        return response


# ── Token refresh (keeps UserSession.jti in sync after rotation) ─────────────

class CustomTokenRefreshView(TokenRefreshView):
    """
    Wraps simplejwt's TokenRefreshView to update the UserSession record
    when a refresh token is rotated (ROTATE_REFRESH_TOKENS=True).
    """

    def post(self, request, *args, **kwargs):
        old_jti = None
        try:
            old_jti = JWTRefreshToken(request.data.get("refresh", ""))["jti"]
        except Exception:
            pass

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200 and old_jti:
            try:
                new_jti = JWTRefreshToken(response.data.get("refresh", ""))["jti"]
                session = UserSession.objects.filter(jti=old_jti, is_active=True).first()
                if session:
                    session.jti = new_jti
                    session.last_active = timezone.now()
                    session.save(update_fields=["jti", "last_active"])

                    # Re-issue access token with session_id claim so is_current stays accurate.
                    new_access = AccessToken(response.data["access"])
                    new_access["session_id"] = session.pk
                    response.data["access"] = str(new_access)
            except Exception:
                logger.exception("Failed to sync UserSession JTI after token rotation (old_jti=%s)", old_jti)

        return response


# ── 2FA ───────────────────────────────────────────────────────────────────────

class TOTPSetupView(APIView):
    """
    GET  /auth/2fa/setup/
    Generates a fresh TOTP secret and returns the otpauth:// URI for QR display.
    The secret is saved to the user but 2FA is NOT enabled until /auth/2fa/enable/.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TOTPActionThrottle]

    def get(self, request):
        user = request.user
        if user.totp_enabled:
            return Response(
                {"detail": "2FA is already enabled. Disable it first to reset."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.save(update_fields=["totp_secret"])

        totp = pyotp.TOTP(secret)
        otpauth_uri = totp.provisioning_uri(name=user.email, issuer_name="PyAnalypt")
        return Response({"secret": secret, "otpauth_uri": otpauth_uri})


class TOTPEnableView(APIView):
    """
    POST /auth/2fa/enable/   { "code": "123456" }
    Verifies the TOTP code against the stored secret and activates 2FA.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TOTPActionThrottle]

    def post(self, request):
        serializer = TOTPEnableSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.totp_enabled = True
        request.user.save(update_fields=["totp_enabled"])
        return Response({"detail": "2FA enabled successfully."})


class TOTPDisableView(APIView):
    """
    POST /auth/2fa/disable/   { "code": "123456", "password": "..." }
    Disables 2FA after verifying both the current password and a valid TOTP code.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TOTPActionThrottle]

    def post(self, request):
        serializer = TOTPDisableSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.totp_enabled = False
        user.totp_secret = ""
        user.save(update_fields=["totp_enabled", "totp_secret"])
        return Response({"detail": "2FA disabled successfully."})


class TOTPVerifyLoginView(APIView):
    """
    POST /auth/2fa/verify-login/   { "totp_token": "...", "code": "123456" }
    Completes a login that was paused for 2FA.
    Returns JWT access + refresh tokens identical to the normal login response.
    """

    permission_classes = [AllowAny]
    throttle_classes = [TOTPVerifyThrottle]

    def post(self, request):
        serializer = TOTPVerifyLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        totp_token = serializer.validated_data["totp_token"]
        code = serializer.validated_data["code"]

        try:
            payload = signing.loads(totp_token, salt="2fa-login", max_age=300)
        except signing.SignatureExpired:
            return Response(
                {"detail": "Token expired, please log in again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Invalid token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=payload["uid"])
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                {"detail": "Account is disabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.totp_secret:
            return Response(
                {"detail": "2FA is not configured for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = JWTRefreshToken.for_user(user)
        refresh_str = str(refresh)
        session = _create_session(request, user, refresh_str)

        access_token = refresh.access_token
        if session:
            access_token["session_id"] = session.pk

        return Response({
            "access": str(access_token),
            "refresh": refresh_str,
            "user": CustomUserDetailsSerializer(user, context={"request": request}).data,
        })


# ── Password change (adds throttle + revokes other sessions) ──────────────────

class CustomPasswordChangeView(PasswordChangeView):
    """
    POST /auth/password/change/
    Wraps dj-rest-auth PasswordChangeView to:
    - Enforce a per-user rate limit.
    - Revoke all active sessions except the current one after a successful change.
    """

    throttle_classes = [PasswordChangeThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            current_session_id = None
            try:
                if hasattr(request, "auth") and request.auth:
                    current_session_id = request.auth.get("session_id")
            except Exception:
                pass
            sessions = UserSession.objects.filter(user=request.user, is_active=True)
            if current_session_id:
                sessions = sessions.exclude(pk=current_session_id)
            for session in sessions:
                _revoke_session(session)
        return response


# ── Sessions ──────────────────────────────────────────────────────────────────

class UserSessionListView(generics.ListAPIView):
    """GET /auth/sessions/  — list all active sessions for the current user."""

    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        try:
            if hasattr(self.request, "auth") and self.request.auth:
                ctx["current_session_id"] = self.request.auth.get("session_id")
        except Exception:
            pass
        return ctx


class UserSessionRevokeView(APIView):
    """DELETE /auth/sessions/{id}/  — revoke a specific session."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        session = get_object_or_404(
            UserSession, pk=pk, user=request.user, is_active=True
        )
        _revoke_session(session)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserSessionRevokeAllView(APIView):
    """
    POST /auth/sessions/revoke-all/
    Revokes ALL active sessions for the current user (forces logout everywhere).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        sessions = list(UserSession.objects.filter(user=request.user, is_active=True))
        for session in sessions:
            _revoke_session(session)
        return Response({"detail": f"Revoked {len(sessions)} session(s)."})
