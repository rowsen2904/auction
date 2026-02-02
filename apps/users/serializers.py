from django.contrib.auth import authenticate, get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .utils import verify_code
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
