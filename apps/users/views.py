import jwt
from deals.models import Deal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from notifications.services import notify_new_broker_registered
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from helpers.file_tokens import (
    build_deal_document_url,
    build_developer_template_url,
    build_user_document_url,
    verify_download_token,
    verify_public_download_token,
)
from helpers.utils import get_client_ip

from .models import Broker, UserDocument
from .schemas import (
    get_verification_code_schema,
    login_schema,
    password_reset_confirm_schema,
    password_reset_request_schema,
    password_reset_verify_schema,
    refresh_schema,
    register_broker_schema,
    resend_code_schema,
    verify_email_schema,
)
from .serializers import (
    ChangePasswordSerializer,
    DeveloperDDUTemplateUploadSerializer,
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    MessageResponseSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetVerifySerializer,
    RegisterBrokerSerializer,
    RegisterResponseSerializer,
    UnifiedDocumentSerializer,
    UserDocumentDeleteSerializer,
    UserDocumentNameUpdateSerializer,
    UserDocumentSerializer,
    UserDocumentsUploadSerializer,
    UserProfileUpdateSerializer,
    VerifyEmailSerializer,
)
from .utils import (
    clear_email_verified_for_password_reset,
    clear_email_verified_for_registration,
    email_rate_limiter,
    login_attempt_limiter,
    mark_email_verified_for_password_reset,
    mark_email_verified_for_registration,
    send_password_reset_email_to,
    send_verification_email_to,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    @login_schema
    def post(self, request, *args, **kwargs):
        ip_address = get_client_ip(request)
        email = (request.data.get("email") or "").strip().lower()

        rate_limit_result = login_attempt_limiter.check(ip_address, email)
        if not rate_limit_result.allowed:
            return Response(
                {
                    "error": rate_limit_result.message,
                    "remaining_time": rate_limit_result.remaining_time,
                    "code": "login_locked",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(rate_limit_result.remaining_time)},
            )

        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            login_attempt_limiter.record_failure(ip_address, email)
            raise

        if 200 <= response.status_code < 300:
            login_attempt_limiter.reset(ip_address, email)
        else:
            login_attempt_limiter.record_failure(ip_address, email)

        return response


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

    @extend_schema(
        summary="Update current user's profile",
        tags=["Auth"],
        request=UserProfileUpdateSerializer,
        responses={200: MeSerializer},
    )
    def patch(self, request, *args, **kwargs):
        user = request.user

        if not getattr(user, "is_active", True):
            return Response(
                {"detail": "Пользователь неактивен."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UserProfileUpdateSerializer(
            data=request.data,
            context={"user_id": user.id, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user.pk)
                serializer.apply(user)
        except IntegrityError:
            return Response(
                {"error": _("Не удалось обновить профиль: конфликт значений.")},
                status=status.HTTP_409_CONFLICT,
            )

        user.refresh_from_db()
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
            url = (
                build_user_document_url(request, document_id=doc.id)
                if doc.document
                else None
            )
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
                url = build_deal_document_url(request, deal_id=deal.id, kind="ddu")
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
                url = build_deal_document_url(
                    request, deal_id=deal.id, kind="payment_proof"
                )
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


class DeveloperDDUTemplateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeveloperDDUTemplateUploadSerializer
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload / replace developer's DDU template",
        tags=["Auth"],
        request=DeveloperDDUTemplateUploadSerializer,
        responses={200: MessageResponseSerializer},
    )
    def put(self, request, *args, **kwargs):
        user = request.user
        developer = getattr(user, "developer", None)
        if developer is None:
            return Response(
                {"detail": _("Только девелопер может загружать шаблон ДДУ.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_file = serializer.validated_data["ddu_template"]

        if developer.ddu_template:
            developer.ddu_template.delete(save=False)

        developer.ddu_template = new_file
        developer.save(update_fields=["ddu_template"])

        url = (
            build_developer_template_url(request, developer_user_id=user.id)
            if developer.ddu_template
            else None
        )

        return Response(
            {
                "message": _("Шаблон ДДУ обновлён."),
                "ddu_template_url": url,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer
    parser_classes = [JSONParser]

    @password_reset_request_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        if not User.objects.filter(email=email, is_active=True).exists():
            return Response(
                {"error": _("Пользователь не найден.")},
                status=status.HTTP_404_NOT_FOUND,
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
            send_password_reset_email_to(email, client_ip)
            return Response(
                {
                    "message": "Код для восстановления пароля отправлен на вашу почту.",
                    "email": email,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Не удалось отправить письмо. Попробуйте позже."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PasswordResetVerifyView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetVerifySerializer
    parser_classes = [JSONParser]

    @password_reset_verify_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        mark_email_verified_for_password_reset(email)

        return Response(
            {"message": "Код подтверждён.", "email": email},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    parser_classes = [JSONParser]

    @password_reset_confirm_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        clear_email_verified_for_password_reset(user.email)

        return Response(
            {"message": _("Пароль успешно изменён.")},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Change current user password",
        tags=["Auth"],
        request=ChangePasswordSerializer,
        responses={200: MessageResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": _("Пароль успешно изменён.")},
            status=status.HTTP_200_OK,
        )


# ----------------------------------------------------------------------
# Auth-gated download endpoints
#
# All file URLs in API responses are emitted as `<base>/api/v1/files/...`
# with a short-lived (10 min) signed JWT in `?t=<token>`. The endpoint
# validates the token, re-checks permissions on the underlying object,
# decrypts the payload via EncryptedFileSystemStorage, and streams it.
# Direct /media/* URLs do not work — files on disk are ciphertext.
# ----------------------------------------------------------------------


def _streaming_response(file_field, filename: str | None = None) -> FileResponse:
    """
    Open `file_field` via its storage (transparently decrypts), and stream
    it back as an attachment. Sets a stable Content-Type best-effort.
    """
    if not file_field:
        raise Http404
    fh = file_field.storage.open(file_field.name, "rb")
    name = filename or fh.name.rsplit("/", 1)[-1]
    return FileResponse(fh, as_attachment=True, filename=name)


def _verify_or_404(request, *, kind: str, ref: str) -> int:
    token = request.GET.get("t")
    if not token:
        raise Http404
    try:
        return verify_download_token(token, kind=kind, ref=ref)
    except jwt.InvalidTokenError:
        raise Http404


class UserDocumentDownloadView(APIView):
    """GET /api/v1/files/user-document/<id>/?t=<token>"""

    permission_classes = [AllowAny]

    def get(self, request, document_id: int):
        uid = _verify_or_404(request, kind="user_doc", ref=str(document_id))
        try:
            doc = UserDocument.objects.select_related("user").get(id=document_id)
        except UserDocument.DoesNotExist:
            raise Http404
        # Token's uid must own the document
        if doc.user_id != uid:
            raise Http404
        return _streaming_response(doc.document, filename=doc.filename)


class DealDocumentDownloadView(APIView):
    """
    GET /api/v1/files/deal/<deal_id>/<kind>/?t=<token>

    kind in {"ddu", "payment_proof"}.
    """

    permission_classes = [AllowAny]

    KIND_TO_FIELD = {
        "ddu": "ddu_document",
        "payment_proof": "payment_proof_document",
    }

    def get(self, request, deal_id: int, kind: str):
        if kind not in self.KIND_TO_FIELD:
            raise Http404
        ref = f"deal:{deal_id}:{kind}"
        uid = _verify_or_404(request, kind=f"deal_{kind}", ref=ref)
        try:
            deal = Deal.objects.select_related("broker", "developer").get(id=deal_id)
        except Deal.DoesNotExist:
            raise Http404
        # Token's uid must be the broker, the developer or any admin
        if uid not in (deal.broker_id, deal.developer_id):
            try:
                u = User.objects.only("id", "role", "is_staff").get(id=uid)
            except User.DoesNotExist:
                raise Http404
            if not (u.is_staff or u.role == User.Roles.ADMIN):
                raise Http404
        field = getattr(deal, self.KIND_TO_FIELD[kind], None)
        return _streaming_response(field)


class DeveloperTemplateDownloadView(APIView):
    """
    GET /api/v1/files/developer/<developer_user_id>/ddu-template/?t=<token>

    Allowed to: the developer themselves, any broker who has a deal with
    that developer, and admins.
    """

    permission_classes = [AllowAny]

    def get(self, request, developer_user_id: int):
        ref = f"developer:{developer_user_id}"
        uid = _verify_or_404(request, kind="developer_template", ref=ref)
        try:
            dev_user = User.objects.select_related("developer").get(
                id=developer_user_id, role=User.Roles.DEVELOPER
            )
        except User.DoesNotExist:
            raise Http404

        # Permission re-check: dev itself, admin, or a broker with a deal w/ this dev
        allowed = uid == dev_user.id
        if not allowed:
            try:
                u = User.objects.only("id", "role", "is_staff").get(id=uid)
            except User.DoesNotExist:
                raise Http404
            if u.is_staff or u.role == User.Roles.ADMIN:
                allowed = True
            elif u.role == User.Roles.BROKER:
                allowed = Deal.objects.filter(broker_id=uid, developer_id=dev_user.id).exists()
        if not allowed:
            raise Http404

        dev = getattr(dev_user, "developer", None)
        if dev is None or not dev.ddu_template:
            raise Http404
        return _streaming_response(dev.ddu_template)


class PropertyImageDownloadView(APIView):
    """
    GET /api/v1/files/property-image/<image_id>/?t=<token>

    Public — property images are visible in the catalog. Files are
    encrypted on disk so the only way to fetch them is through this view.
    """

    permission_classes = [AllowAny]

    def get(self, request, image_id: int):
        from properties.models import PropertyImage

        token = request.GET.get("t")
        if not token:
            raise Http404
        try:
            verify_public_download_token(
                token, kind="property_image", ref=str(image_id)
            )
        except jwt.InvalidTokenError:
            raise Http404

        try:
            image = PropertyImage.objects.only("id", "image").get(id=image_id)
        except PropertyImage.DoesNotExist:
            raise Http404
        if not image.image:
            raise Http404

        fh = image.image.storage.open(image.image.name, "rb")
        name = fh.name.rsplit("/", 1)[-1]
        return FileResponse(fh, as_attachment=False, filename=name)


class DocumentRequestFileDownloadView(APIView):
    """
    GET /api/v1/files/document-request/<file_id>/?t=<token>

    Authorized: the auction owner, the broker who answered the request,
    the admin, or the user who originally requested the documents.
    """

    permission_classes = [AllowAny]

    def get(self, request, file_id: int):
        from auctions.models import DocumentRequestFile

        uid = _verify_or_404(
            request, kind="document_request_file", ref=str(file_id)
        )
        try:
            doc = (
                DocumentRequestFile.objects.select_related(
                    "request",
                    "request__auction",
                    "request__broker",
                    "request__requested_by",
                )
                .only(
                    "id",
                    "file",
                    "request__auction__owner_id",
                    "request__broker_id",
                    "request__requested_by_id",
                )
                .get(id=file_id)
            )
        except DocumentRequestFile.DoesNotExist:
            raise Http404

        allowed_uids = {
            doc.request.auction.owner_id,
            doc.request.broker_id,
            doc.request.requested_by_id,
        }
        if uid not in allowed_uids:
            try:
                u = User.objects.only("id", "role", "is_staff").get(id=uid)
            except User.DoesNotExist:
                raise Http404
            if not (u.is_staff or u.role == User.Roles.ADMIN):
                raise Http404

        return _streaming_response(doc.file)


class SettlementDocumentDownloadView(APIView):
    """
    GET /api/v1/files/settlement/<settlement_id>/<kind>/?t=<token>

    kind in {"broker_payout_receipt", "developer_receipt"}.
    Allowed: the deal's broker, the deal's developer, and admins.
    """

    permission_classes = [AllowAny]

    KIND_TO_FIELD = {
        "broker_payout_receipt": "broker_payout_receipt",
        "developer_receipt": "developer_receipt",
    }

    def get(self, request, settlement_id: int, kind: str):
        if kind not in self.KIND_TO_FIELD:
            raise Http404
        ref = f"settlement:{settlement_id}:{kind}"
        uid = _verify_or_404(request, kind=f"settlement_{kind}", ref=ref)

        from payments.models import DealSettlement

        try:
            settlement = (
                DealSettlement.objects.select_related("deal__broker", "deal__developer")
                .only(
                    "id",
                    "broker_payout_receipt",
                    "developer_receipt",
                    "deal__broker_id",
                    "deal__developer_id",
                )
                .get(id=settlement_id)
            )
        except DealSettlement.DoesNotExist:
            raise Http404

        if uid not in (settlement.deal.broker_id, settlement.deal.developer_id):
            try:
                u = User.objects.only("id", "role", "is_staff").get(id=uid)
            except User.DoesNotExist:
                raise Http404
            if not (u.is_staff or u.role == User.Roles.ADMIN):
                raise Http404

        field = getattr(settlement, self.KIND_TO_FIELD[kind], None)
        return _streaming_response(field)
