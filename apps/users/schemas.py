from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .serializers import (
    LoginSerializer,
    EmailSerializer,
    VerifyEmailSerializer,
    MessageEmailResponseSerializer,
    MessageResponseSerializer,
    RateLimitResponseSerializer,
    ErrorResponseSerializer,
    RegisterBrokerSerializer,
    RegisterDeveloperSerializer,
    RegisterResponseSerializer,
)

LOGIN_DOC = _("Obtain JWT token pair.")
REFRESH_DOC = _("Takes a refresh token and returns a new access token.")

GET_CODE_DOC = (
    "Sends a numeric OTP verification code to the provided email address.\n\n"
    "**Important:** This endpoint does **not** create a user account."
)

VERIFY_EMAIL_DOC = (
    "Verifies the OTP code for the given email address.\n\n"
    "- Returns **200** if the code is valid\n"
    "- Returns **400** if the code is invalid or expired\n\n"
    "**Important:** This endpoint does **not** create a user account and does **not** return JWT tokens."
)

RESEND_CODE_DOC = (
    "Sends a new OTP verification code to the provided email address.\n\n"
    "**Important:** This endpoint does **not** create a user account."
)

REGISTER_DEVELOPER_DOC = (
    "Registers a new user with role **developer**.\n\n"
    "Requirements:\n"
    "- Email must be verified via OTP beforehand.\n"
    "- Admin role cannot be selected.\n"
    "- `company_name` is required."
)

REGISTER_BROKER_DOC = (
    "Registers a new user with role **broker** and creates a **Broker** profile.\n\n"
    "Requirements:\n"
    "- Email must be verified via OTP beforehand.\n"
    "- Must provide `inn_number`.\n"
    "- Must upload `inn` and `passport`.\n"
    "- Broker is created with `is_verified=false` and `verification_status=pending`."
)

login_schema = extend_schema(
    request=LoginSerializer,
    responses=LoginSerializer,
    description=LOGIN_DOC,
    tags=["Auth"],
)

refresh_schema = extend_schema(
    request=TokenRefreshSerializer,
    responses=TokenRefreshSerializer,
    description=REFRESH_DOC,
    tags=["Auth"],
)

get_verification_code_schema = extend_schema(
    summary="Request verification code",
    description=GET_CODE_DOC,
    request=EmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Verification code sent.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"message": "Verification code sent to your email.", "email": "user@example.com"},
                )
            ],
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="User already exists.",
            examples=[
                OpenApiExample(
                    "User already exists",
                    value={"error": "User already exists."},
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

verify_email_schema = extend_schema(
    summary="Verify email code",
    description=VERIFY_EMAIL_DOC,
    request=VerifyEmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Email code verified.",
            examples=[
                OpenApiExample(
                    "Verified",
                    value={"message": "Email verified successfully.", "email": "user@example.com"},
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

resend_code_schema = extend_schema(
    summary="Resend verification code",
    description=RESEND_CODE_DOC,
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

register_developer_schema = extend_schema(
    summary="Register developer",
    description=REGISTER_DEVELOPER_DOC,
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
                        "refresh": "some_refresh_token",
                        "access": "some_access_token",
                        "user": {
                            "id": 1,
                            "email": "user@example.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "role": "developer",
                            "broker": None,
                            "developer": {
                                "company_name": "Acme Inc",
                            },
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

register_broker_schema = extend_schema(
    summary="Register broker",
    description=REGISTER_BROKER_DOC,
    request=RegisterBrokerSerializer,
    responses={
        201: OpenApiResponse(
            response=RegisterResponseSerializer,
            description="Broker registered.",
            examples=[
                OpenApiExample(
                    "Created",
                    value={
                        "message": "Registration successful.",
                        "refresh": "some_refresh_token",
                        "access": "some_access_token",
                        "user": {
                            "id": 2,
                            "email": "broker@example.com",
                            "first_name": "Alice",
                            "last_name": "Smith",
                            "role": "broker",
                            "broker": {
                                "is_verified": False,
                                "verification_status": "pending",
                                "verified_at": None,
                                "inn_number": "772158104012",
                                "inn_url": "http://host:7676/media/...",
                                "passport_url": "http://host:7676/media/...",
                            },
                            "developer": None,
                        },
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error (e.g., email not verified, missing files, invalid INN).",
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="User already exists.",
        ),
    },
    tags=["Auth"],
)
