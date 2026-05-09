import pyotp

from dj_rest_auth.serializers import UserDetailsSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator

from .models import UserSession
from .utils import validate_birthday_not_future

User = get_user_model()


# ── Registration ─────────────────────────────────────────────────────────────

class InitialRegisterSerializer(serializers.Serializer):
    """
    Step 1: Registration with email and password only.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        normalized = value.strip().lower()
        existing = User.objects.filter(email__iexact=normalized).first()
        if existing:
            if not existing.email_verified and not existing.is_active:
                raise serializers.ValidationError(
                    "An unverified account already exists with this email. "
                    "Please check your inbox or use the resend-otp endpoint to get a new code."
                )
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate(self, data):
        try:
            validate_password(data["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return data


class ResendOTPSerializer(serializers.Serializer):
    """
    Serializer for resending registration OTP.
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class CompleteProfileSerializer(serializers.Serializer):
    """
    Step 3: Profile completion with username, full name, and birthday.
    """

    username = serializers.CharField(
        min_length=3,
        max_length=150,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9._-]+$",
                message="Username can only contain letters, numbers, dots, underscores, and hyphens.",
            )
        ],
    )
    full_name = serializers.CharField(
        min_length=2,
        max_length=255,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-ZÀ-ÿ'\- ]+$",
                message="Only letters, hyphens, apostrophes, and spaces are allowed.",
            )
        ],
    )
    birthday = serializers.DateField(
        validators=[validate_birthday_not_future],
        error_messages={'invalid': 'Invalid date format. Use YYYY-MM-DD.'}
    )

    def validate_username(self, value):
        user = self.context['request'].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value


# ── OTP Verification ──────────────────────────────────────────────────────────

class RegistrationOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(
        min_length=6,
        max_length=6,
        validators=[RegexValidator(r"^\d{6}$", "OTP must be exactly 6 digits.")],
    )

    def validate_email(self, value):
        return value.strip().lower()


# ── User profile ─────────────────────────────────────────────────────────────

class CustomUserDetailsSerializer(UserDetailsSerializer):
    """
    Returned on login, registration, and GET/PATCH /auth/user/.
    Writable: username, full_name, birthday, profile_picture.
    Read-only: email and all account-state fields.
    """

    birthday = serializers.DateField(validators=[validate_birthday_not_future])

    class Meta(UserDetailsSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "username",
            "full_name",
            "birthday",
            "profile_picture",
            "email_verified",
            "is_staff",
            "is_active",
            "date_joined",
            "last_login",
        )
        read_only_fields = (
            "id",
            "email",
            "email_verified",
            "is_staff",
            "is_active",
            "date_joined",
            "last_login",
        )

    def validate_username(self, value):
        user = self.context["request"].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_profile_picture(self, value):
        """
        Handle the case where the frontend sends an empty string to 'clear' the picture.
        In multipart/form-data, an empty file input sends an empty string.
        """
        if value == "":
            return None
        return value


# ── Sessions ─────────────────────────────────────────────────────────────────

class UserSessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = ("id", "device", "browser", "ip_address", "created_at", "last_active", "is_current")
        read_only_fields = ("id", "device", "browser", "ip_address", "created_at", "last_active", "is_current")

    def get_is_current(self, obj):
        return obj.pk == self.context.get("current_session_id")


# ── 2FA ──────────────────────────────────────────────────────────────────────

_DIGITS_ONLY = RegexValidator(r'^\d{6}$', 'Code must be exactly 6 digits.')


class TOTPEnableSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6, validators=[_DIGITS_ONLY])

    def validate_code(self, value):
        user = self.context["request"].user
        if user.totp_enabled:
            raise serializers.ValidationError("2FA is already enabled.")
        if not user.totp_secret:
            raise serializers.ValidationError(
                "Run GET /auth/2fa/setup/ first to generate a secret."
            )
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(value, valid_window=1):
            raise serializers.ValidationError("Invalid or expired code.")
        return value


class TOTPDisableSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6, validators=[_DIGITS_ONLY])
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = self.context["request"].user
        if not user.totp_enabled:
            raise serializers.ValidationError("2FA is not enabled on this account.")
        if not user.check_password(data["password"]):
            raise serializers.ValidationError({"password": "Incorrect password."})
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(data["code"], valid_window=1):
            raise serializers.ValidationError({"code": "Invalid or expired code."})
        return data


class TOTPVerifyLoginSerializer(serializers.Serializer):
    totp_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=6, validators=[_DIGITS_ONLY])
