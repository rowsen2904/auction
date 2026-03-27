from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from helpers.utils import get_client_ip

from .models import Broker, Developer, UserDocument
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
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    MessageResponseSerializer,
    RegisterBrokerSerializer,
    RegisterDeveloperSerializer,
    RegisterResponseSerializer,
    UserDocumentDeleteSerializer,
    UserDocumentNameUpdateSerializer,
    UserDocumentSerializer,
    UserDocumentsUploadSerializer,
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
                {"message": "New code sent to your email."},
                status=status.HTTP_200_OK,
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
                    user=user,
                    company_name=company_name,
                )
                user.developer = developer

            clear_email_verified_for_registration(email)
            payload = RegisterResponseSerializer.build_payload(user)
            return Response(payload, status=status.HTTP_201_CREATED)

        except IntegrityError:
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
                    inn_number=inn_number,
                    is_active=True,
                )

                broker = Broker.objects.create(user=user)
                user.broker = broker

                UserDocument.objects.create(
                    user=user,
                    doc_type=UserDocument.Types.INN,
                    document=inn,
                    document_name=inn.name.rsplit(".", 1)[0],
                )
                UserDocument.objects.create(
                    user=user,
                    doc_type=UserDocument.Types.PASSPORT,
                    document=passport,
                    document_name=passport.name.rsplit(".", 1)[0],
                )

            clear_email_verified_for_registration(email)
            payload = RegisterResponseSerializer.build_payload(user)
            return Response(payload, status=status.HTTP_201_CREATED)

        except IntegrityError:
            return Response(
                {"error": _("User already exists.")},
                status=status.HTTP_409_CONFLICT,
            )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user",
        tags=["Auth"],
        responses={200: MeSerializer},
    )
    def get(self, request, *args, **kwargs):
        user = request.user

        if not getattr(user, "is_active", True):
            return Response(
                {"detail": "User is inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            MeSerializer(user, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class UserDocumentsUploadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserDocumentsUploadSerializer
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload user document",
        tags=["Auth"],
        request=UserDocumentsUploadSerializer,
        responses={200: UserDocumentSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        return Response(
            {
                "message": _("Документ успешно загружен."),
                "document": UserDocumentSerializer(
                    document,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class UserDocumentNameUpdateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserDocumentNameUpdateSerializer

    @extend_schema(
        summary="Update user document name",
        tags=["Auth"],
        request=UserDocumentNameUpdateSerializer,
        responses={200: UserDocumentSerializer},
    )
    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        return Response(
            {
                "message": _("Название документа успешно обновлено."),
                "document": UserDocumentSerializer(
                    document,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class UserDocumentDeleteView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserDocumentDeleteSerializer

    @extend_schema(
        summary="Delete user document",
        tags=["Auth"],
        responses={200: MessageResponseSerializer},
    )
    def delete(self, request, *args, **kwargs):
        serializer = self.get_serializer(data={"document_id": kwargs["document_id"]})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": _("Документ успешно удалён.")},
            status=status.HTTP_200_OK,
        )
