from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from helpers.utils import get_client_ip

from .models import Broker, Developer
from .schemas import (
    get_verification_code_schema,
    login_schema,
    refresh_schema,
    register_broker_schema,
    register_developer_schema,
    resend_code_schema,
    verify_email_schema,
)
from .serializers import (
    BrokerVerificationSerializer,
    EmailSerializer,
    LoginSerializer,
    RegisterBrokerSerializer,
    RegisterDeveloperSerializer,
    RegisterResponseSerializer,
    VerifyEmailSerializer,
)
from .utils import (
    clear_email_verified_for_registration,
    email_rate_limiter,
    mark_email_verified_for_registration,
    send_verification_email_to,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    @login_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    @refresh_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class GetVerificationCodeView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer

    @get_verification_code_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": _("User already exists.")},
                status=status.HTTP_409_CONFLICT,
            )

        rate_limit_result = email_rate_limiter.check_rate_limit(client_ip, email)
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
        except Exception:
            return Response(
                {"error": "Failed to send email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyEmailView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer

    @verify_email_schema
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


class ResendCodeView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer

    @resend_code_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        rate_limit_result = email_rate_limiter.check_rate_limit(client_ip, email)
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
                {"message": "New code sent to your email."}, status=status.HTTP_200_OK
            )
        except Exception:
            return Response(
                {"error": "Failed to send email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RegisterDeveloperView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterDeveloperSerializer
    parser_classes = [JSONParser]

    @register_developer_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        first_name = serializer.validated_data.get("first_name", "")
        last_name = serializer.validated_data.get("last_name", "")
        company_name = serializer.validated_data.get("company_name", "")

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

                developer = Developer.objects.create(
                    user=user, company_name=company_name
                )

                # Cache the relation on the user instance to avoid an extra DB query in serializer
                user.developer = developer

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


class RegisterBrokerView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterBrokerSerializer
    parser_classes = [MultiPartParser, FormParser]

    @register_broker_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        first_name = serializer.validated_data.get("first_name", "")
        last_name = serializer.validated_data.get("last_name", "")
        inn_number = serializer.validated_data["inn_number"]
        inn = serializer.validated_data["inn"]
        passport = serializer.validated_data["passport"]

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=User.Roles.BROKER,
                    is_active=True,
                )

                broker = Broker.objects.create(
                    user=user,
                    inn_number=inn_number,
                    inn=inn,
                    passport=passport,
                )

                # Cache the relation on the user instance to avoid an extra DB query in serializer
                user.broker = broker

            # One-time use of verified flag
            clear_email_verified_for_registration(email)

            payload = RegisterResponseSerializer.build_payload(user)
            return Response(payload, status=status.HTTP_201_CREATED)

        except IntegrityError as e:
            print(e)
            return Response(
                {"error": f"{e}"},
                status=status.HTTP_409_CONFLICT,
            )


class BrokerVerificationView(generics.GenericAPIView):
    queryset = (
        User.objects.select_related("broker")
        .only("id", "role", "broker__id", "broker__verification_status")
        .filter(role=User.Roles.BROKER)
    )
    serializer_class = BrokerVerificationSerializer
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["id"]
        action = serializer.validated_data["action"]

        user = get_object_or_404(self.get_queryset(), id=user_id)

        broker = getattr(user, "broker", None)
        if broker is None:
            # Broker profile missing even though role is broker
            raise ValidationError({"id": _("Broker profile not found for this user.")})

        if action == "accept":
            broker.verify_broker()
            msg = _("Broker has been successfully verified.")
        else:
            broker.set_as_rejected()
            msg = _("Broker has been rejected.")

        return Response({"message": msg}, status=status.HTTP_200_OK)
