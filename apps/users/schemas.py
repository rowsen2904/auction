from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .serializers import (
    EmailSerializer,
    ErrorResponseSerializer,
    LoginSerializer,
    MessageEmailResponseSerializer,
    MessageResponseSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetVerifySerializer,
    RateLimitResponseSerializer,
    RegisterBrokerSerializer,
    RegisterResponseSerializer,
    VerifyEmailSerializer,
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

REGISTER_BROKER_DOC = (
    "Registers a new user with role **broker** and creates a **Broker** profile.\n\n"
    "Requirements:\n"
    "- Email must be verified via OTP beforehand.\n"
    "- Must provide `inn_number`.\n"
    "- Must upload `inn` and `passport`.\n"
    "- Uploaded files are stored as `UserDocument` records attached to the user.\n"
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
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer, description="User already exists."
        ),
        429: OpenApiResponse(
            response=RateLimitResponseSerializer, description="Rate limit exceeded."
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
            response=MessageEmailResponseSerializer, description="Email code verified."
        ),
        400: OpenApiResponse(description="Invalid or expired code."),
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
        ),
        429: OpenApiResponse(
            response=RateLimitResponseSerializer, description="Rate limit exceeded."
        ),
    },
    tags=["Auth"],
)

PASSWORD_RESET_REQUEST_DOC = (
    "Sends a numeric OTP code to an existing user's email for password reset.\n\n"
    "- Returns **200** if the code was sent\n"
    "- Returns **404** if no active user with that email exists\n"
    "- Returns **429** on rate-limit\n\n"
    "**Important:** This endpoint does **not** change the password."
)

PASSWORD_RESET_VERIFY_DOC = (
    "Verifies the OTP code for password reset.\n\n"
    "On success marks the email as verified for password reset within a short TTL,\n"
    "allowing a follow-up call to `password-reset/confirm/` to set a new password.\n\n"
    "**Important:** This endpoint does **not** change the password."
)

PASSWORD_RESET_CONFIRM_DOC = (
    "Sets a new password for a user whose email was verified via\n"
    "`password-reset/request/` + `password-reset/verify/`.\n\n"
    "Requirements:\n"
    "- Email must be verified for password reset beforehand (short-lived flag).\n"
    "- `new_password` must pass Django password validators.\n"
    "- `new_password` must equal `new_password_confirm`."
)

password_reset_request_schema = extend_schema(
    summary="Request password reset code",
    description=PASSWORD_RESET_REQUEST_DOC,
    request=EmailSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Password reset code sent.",
        ),
        404: OpenApiResponse(
            response=ErrorResponseSerializer, description="User not found."
        ),
        429: OpenApiResponse(
            response=RateLimitResponseSerializer, description="Rate limit exceeded."
        ),
    },
    tags=["Auth"],
)

password_reset_verify_schema = extend_schema(
    summary="Verify password reset code",
    description=PASSWORD_RESET_VERIFY_DOC,
    request=PasswordResetVerifySerializer,
    responses={
        200: OpenApiResponse(
            response=MessageEmailResponseSerializer,
            description="Password reset code verified.",
        ),
        400: OpenApiResponse(description="Invalid or expired code."),
    },
    tags=["Auth"],
)

password_reset_confirm_schema = extend_schema(
    summary="Confirm password reset",
    description=PASSWORD_RESET_CONFIRM_DOC,
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(
            response=MessageResponseSerializer, description="Password has been reset."
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error (email not verified, password mismatch, weak password).",
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
                                "rejected_at": None,
                                "verified_at": None,
                                "inn_number": "772158104012",
                            },
                            "developer": None,
                            "documents": [
                                {
                                    "id": 10,
                                    "doc_type": "inn",
                                    "document_name": "inn_file",
                                    "url": "http://host:8000/media/users/2/documents/abc.pdf",
                                    "filename": "abc.pdf",
                                    "extension": ".pdf",
                                    "created_at": "2026-03-26T10:00:00Z",
                                    "updated_at": "2026-03-26T10:00:00Z",
                                },
                                {
                                    "id": 11,
                                    "doc_type": "passport",
                                    "document_name": "passport_file",
                                    "url": "http://host:8000/media/users/2/documents/def.pdf",
                                    "filename": "def.pdf",
                                    "extension": ".pdf",
                                    "created_at": "2026-03-26T10:00:00Z",
                                    "updated_at": "2026-03-26T10:00:00Z",
                                },
                            ],
                        },
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer, description="Validation error."
        ),
        409: OpenApiResponse(
            response=ErrorResponseSerializer, description="User already exists."
        ),
    },
    tags=["Auth"],
)
