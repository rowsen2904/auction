from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    LoginSerializer,
    EmailSerializer,
    VerifyEmailSerializer,
    MessageEmailResponseSerializer,
    MessageResponseSerializer,
    RateLimitResponseSerializer,
    ErrorResponseSerializer,
    RegisterDeveloperSerializer,
    RegisterResponseSerializer,
    TokenUserSerializer
)
from .utils import (
    email_rate_limiter,
    send_verification_email_to,
    mark_email_verified_for_registration,
    clear_email_verified_for_registration
)
from helpers.utils import get_client_ip

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses=LoginSerializer,
        description=_("Obtain JWT token pair."),
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    @extend_schema(
        request=TokenRefreshSerializer,
        responses=TokenRefreshSerializer,
        description=_(
            "Takes a refresh type JSON web token and returns an access type JSON web token if the refresh token is valid."),
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(
    summary="Request verification code",
    description=(
        "Sends a numeric OTP verification code to the provided email address.\n\n"
        "**Important:** This endpoint does **not** create a user account."
    ),
    request=EmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Verification code sent.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"message": "Verification code sent to your email.",
                           "email": "user@example.com"},
                )
            ],
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="User is already exists.",
            examples=[
                OpenApiExample(
                    "User is already exists",
                    value={
                        "error": "User is already exists.",
                    },
                )
            ],
        ),
        429: OpenApiResponse(
            response=RateLimitResponseSerializer,
            description="Rate limit exceeded.",
            examples=[
                OpenApiExample(
                    "Rate limited",
                    value={
                        "error": "Please wait 42 seconds before requesting another code.",
                        "remaining_time": 42,
                        "code": "rate_limit_exceeded",
                    },
                )
            ],
        ),
    },
    tags=["Auth"],
)
class GetVerificationCodeView(generics.GenericAPIView):
    """Request an email OTP code (no user creation)."""
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        if User.objects.filter(email=email).exists():
            return Response(
                {"message": _("User is already exists.")},
                status=status.HTTP_409_CONFLICT,
            )

        rate_limit_result = email_rate_limiter.check_rate_limit(
            client_ip, email)
        if not rate_limit_result.allowed:
            return Response(
                {
                    "error": rate_limit_result.message,
                    "remaining_time": rate_limit_result.remaining_time,
                    "code": "rate_limit_exceeded",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            send_verification_email_to(email, client_ip)
            return Response(
                {"message": "Verification code sent to your email.", "email": email},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to send email. Please try again later. {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Verify email code",
    description=(
        "Verifies the OTP code for the given email address.\n\n"
        "- Returns **200** if the code is valid\n"
        "- Returns **400** if the code is invalid or expired\n\n"
        "**Important:** This endpoint does **not** create a user account and does **not** return JWT tokens."
    ),
    request=VerifyEmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Email code verified.",
            examples=[
                OpenApiExample(
                    "Verified",
                    value={"message": "Email verified successfully.",
                           "email": "user@example.com"},
                )
            ],
        ),
        400: OpenApiResponse(
            description="Invalid or expired code.",
            examples=[
                OpenApiExample(
                    "Invalid code",
                    value={"code": ["Invalid or expired code"]},
                )
            ],
        ),
    },
    tags=["Auth"],
)
class VerifyEmailView(generics.GenericAPIView):
    """Verify OTP code only (no user creation, no tokens)."""
    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        # Allow registration for a limited time window after OTP verification
        mark_email_verified_for_registration(email)

        return Response(
            {"message": "Email verified successfully.", "email": email},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Resend verification code",
    description=(
        "Sends a new OTP verification code to the provided email address.\n\n"
        "**Important:** This endpoint does **not** create a user account."
    ),
    request=EmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageResponseSerializer,
            description="New verification code sent.",
            examples=[
                OpenApiExample(
                    "Resent",
                    value={"message": "New code sent to your email."},
                )
            ],
        ),
        429: OpenApiResponse(
            response=RateLimitResponseSerializer,
            description="Rate limit exceeded.",
        ),
    },
    tags=["Auth"],
)
class ResendCodeView(generics.GenericAPIView):
    """Resend email OTP code (no user creation)."""
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        rate_limit_result = email_rate_limiter.check_rate_limit(
            client_ip, email)
        if not rate_limit_result.allowed:
            return Response(
                {
                    "error": rate_limit_result.message,
                    "remaining_time": rate_limit_result.remaining_time,
                    "code": "rate_limit_exceeded",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            send_verification_email_to(email, client_ip)
            return Response(
                {"message": "New code sent to your email."},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Failed to send email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# Register views

@extend_schema(
    summary="Register developer",
    description=(
        "Registers a new user with role **developer**.\n\n"
        "Requirements:\n"
        "- Email must be verified via OTP beforehand.\n"
        "- Admin role cannot be selected."
    ),
    request=RegisterDeveloperSerializer,
    responses={
        201: OpenApiResponse(
            response=RegisterResponseSerializer,
            description="Developer registered.",
            examples=[
                OpenApiExample(
                    "Created",
                    value={
                        "message": "Registration successful.",
                        "refresh_token": "Some refresh token.",
                        "access_token": "Some access token.",
                        "user": {
                            "id": 1,
                            "email": "user@example.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "role": "developer",
                        },
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error (e.g., email not verified).",
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="User already exists.",
        ),
    },
    tags=["Auth"],
)
class RegisterDeveloperView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterDeveloperSerializer
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        first_name = serializer.validated_data.get("first_name", "")
        last_name = serializer.validated_data.get("last_name", "")

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=User.Roles.DEVELOPER,
                    is_active=True,
                )

            # One-time use of verified flag
            clear_email_verified_for_registration(email)
            payload = RegisterResponseSerializer.build_payload(user)
            return Response(payload, status=status.HTTP_201_CREATED)
        except IntegrityError:
            # Handles race condition if two requests try to create the same email concurrently
            return Response(
                {"error": _("User already exists.")},
                status=status.HTTP_409_CONFLICT,
            )
