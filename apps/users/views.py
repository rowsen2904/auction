from deals.models import Deal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from notifications.services import notify_new_broker_registered
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
    UnifiedDocumentSerializer,
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
                {"error": _("Пользователь уже существует.")},
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
                {
                    "message": "Код подтверждения отправлен на вашу почту.",
                    "email": email,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Не удалось отправить письмо. Попробуйте позже."},
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
            {"message": "Email успешно подтверждён.", "email": email},
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
                {"message": "Новый код отправлен на вашу почту."},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Не удалось отправить письмо. Попробуйте позже."},
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
                {"error": _("Пользователь уже существует.")},
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
        phone_number = serializer.validated_data.get("phone_number", "")
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

                broker = Broker.objects.create(user=user, phone_number=phone_number)
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

            notify_new_broker_registered(broker_user=user)
            clear_email_verified_for_registration(email)
            payload = RegisterResponseSerializer.build_payload(user)
            return Response(payload, status=status.HTTP_201_CREATED)

        except IntegrityError:
            return Response(
                {"error": _("Пользователь уже существует.")},
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
                {"detail": "Пользователь неактивен."},
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


class AllDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get all user documents (personal + deal)",
        tags=["Auth"],
        responses={200: UnifiedDocumentSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        results = []

        # 1) Personal documents (UserDocument)
        for doc in UserDocument.objects.filter(user=user).order_by("-created_at"):
            url = doc.document.url if doc.document else None
            if url and request:
                url = request.build_absolute_uri(url)
            results.append(
                {
                    "id": doc.id,
                    "source": "user",
                    "doc_type": doc.doc_type,
                    "document_name": doc.document_name or doc.filename,
                    "url": url,
                    "filename": doc.filename,
                    "extension": doc.extension,
                    "created_at": doc.created_at,
                    "deal_id": None,
                    "deal_status": None,
                    "property_address": None,
                }
            )

        # 2) Deal documents (DDU + payment proof)
        deals = (
            Deal.objects.filter(Q(broker=user) | Q(developer=user))
            .select_related("real_property")
            .order_by("-created_at")
        )

        for deal in deals:
            address = getattr(deal.real_property, "address", "")

            if deal.ddu_document:
                fname = deal.ddu_document.name.rsplit("/", 1)[-1]
                ext = f".{fname.rsplit('.', 1)[-1].lower()}" if "." in fname else ""
                url = request.build_absolute_uri(deal.ddu_document.url)
                results.append(
                    {
                        "id": deal.id * 10000 + 1,  # unique synthetic id
                        "source": "deal",
                        "doc_type": "ddu",
                        "document_name": "ДДУ",
                        "url": url,
                        "filename": fname,
                        "extension": ext,
                        "created_at": deal.updated_at,
                        "deal_id": deal.id,
                        "deal_status": deal.status,
                        "property_address": address,
                    }
                )

            if deal.payment_proof_document:
                fname = deal.payment_proof_document.name.rsplit("/", 1)[-1]
                ext = f".{fname.rsplit('.', 1)[-1].lower()}" if "." in fname else ""
                url = request.build_absolute_uri(deal.payment_proof_document.url)
                results.append(
                    {
                        "id": deal.id * 10000 + 2,  # unique synthetic id
                        "source": "deal",
                        "doc_type": "payment_proof",
                        "document_name": "Подтверждение оплаты",
                        "url": url,
                        "filename": fname,
                        "extension": ext,
                        "created_at": deal.updated_at,
                        "deal_id": deal.id,
                        "deal_status": deal.status,
                        "property_address": address,
                    }
                )

        # Sort all by created_at desc
        results.sort(key=lambda x: x["created_at"], reverse=True)

        serializer = UnifiedDocumentSerializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
