from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .utils import verify_code, is_email_verified_for_registration
from auction.settings import EMAIL_VERIFICATION_CODE_LENGTH

User = get_user_model()


class TokenUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    role = serializers.CharField(
        allow_null=True,
        required=False,
        read_only=True
    )


class LoginSerializer(TokenObtainPairSerializer):
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    user = TokenUserSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.username_field in self.fields:
            self.fields[self.username_field].write_only = True

    def validate(self, attrs):
        User = get_user_model()

        identifier = attrs.get(self.username_field)
        password = attrs.get("password")

        if not identifier or not password:
            raise AuthenticationFailed(
                _("Please provide credentials."),
                code="missing_credentials"
            )

        if not User._default_manager.filter(**{self.username_field: identifier}).exists():
            raise AuthenticationFailed(
                _("User not found."),
                code="user_not_found"
            )

        user = authenticate(
            request=self.context.get("request"),
            **{self.username_field: identifier, "password": password},
        )
        if user is None:
            raise AuthenticationFailed(
                _("Invalid credentials."),
                code="invalid_credentials"
            )

        refresh = self.get_token(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": TokenUserSerializer(user).data,
        }


class EmailSerializer(serializers.Serializer):
    """Email input serializer."""
    email = serializers.EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    """
    Verify email OTP code serializer.

    IMPORTANT:
    - No user creation
    - Only validates the OTP
    """
    email = serializers.EmailField()
    code = serializers.CharField(
        max_length=EMAIL_VERIFICATION_CODE_LENGTH,
        min_length=EMAIL_VERIFICATION_CODE_LENGTH,
        required=True,
        help_text=f"{EMAIL_VERIFICATION_CODE_LENGTH}-digit OTP code"
    )

    def validate(self, data):
        if not verify_code(data["email"], data["code"]):
            raise serializers.ValidationError(
                {"code": "Invalid or expired code"})
        return data


# Register serializers


class BaseRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
    )

    first_name = serializers.CharField(
        required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(
        required=False, allow_blank=True, max_length=150)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()

        if not is_email_verified_for_registration(email):
            raise serializers.ValidationError(
                _("Email is not verified."), code="email_not_verified")

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                _("User already exists."), code="email_already_registered")

        return email

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": [_("Passwords do not match.")]},
                code="passwords_do_not_match",
            )

        # Run Django password validators (AUTH_PASSWORD_VALIDATORS)
        try:
            validate_password(password=password, user=None)
        except DjangoValidationError as e:
            # e.messages is a list of validator messages
            raise serializers.ValidationError(
                {"password": e.messages}, code="password_invalid")

        return attrs


class RegisterDeveloperSerializer(BaseRegisterSerializer):
    """
    Registers a developer user (role=developer).
    Email must be verified via OTP beforehand.
    """
    pass


# --- Response serializers (nice Swagger) ---

class MessageEmailResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    email = serializers.EmailField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class RateLimitResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    remaining_time = serializers.IntegerField()
    code = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class RegisterResponseSerializer(TokenObtainPairSerializer):
    message = serializers.CharField()
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    user = TokenUserSerializer()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # TokenObtainPairSerializer normally adds username/password input fields.
        # For registration response, we don't want them.
        self.fields.pop(self.username_field, None)
        self.fields.pop("password", None)

    @classmethod
    def build_payload(cls, user, message: str = "Registration successful."):
        refresh = cls.get_token(user)
        return {
            "message": message,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": TokenUserSerializer(user).data,
        }
