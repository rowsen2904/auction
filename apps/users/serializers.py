from django.contrib.auth import authenticate, get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


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
