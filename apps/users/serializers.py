import os

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from helpers.validators import FileSizeValidationMixin
from migtender.settings import EMAIL_VERIFICATION_CODE_LENGTH

from .models import Broker, Developer, UserDocument
from .utils import is_email_verified_for_registration, verify_code
from .validators import validate_inn

User = get_user_model()


class UserDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    filename = serializers.CharField(read_only=True)
    extension = serializers.CharField(read_only=True)

    class Meta:
        model = UserDocument
        fields = (
            "id",
            "doc_type",
            "document_name",
            "url",
            "filename",
            "extension",
            "created_at",
            "updated_at",
        )

    def get_url(self, obj):
        if not obj.document:
            return None
        request = self.context.get("request")
        url = obj.document.url
        return request.build_absolute_uri(url) if request else url


class TokenUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    role = serializers.CharField(allow_null=True, required=False, read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    broker = serializers.SerializerMethodField()
    developer = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    def get_broker(self, obj):
        broker = getattr(obj, "broker", None)
        if not broker:
            return None
        return BrokerInfoSerializer(broker, context=self.context).data

    def get_developer(self, obj):
        developer = getattr(obj, "developer", None)
        if not developer:
            return None
        return DeveloperInfoSerializer(developer, context=self.context).data

    def get_documents(self, obj):
        if obj.role == User.Roles.ADMIN:
            return []
        return UserDocumentSerializer(
            obj.documents.all(),
            many=True,
            context=self.context,
        ).data


class LoginSerializer(TokenObtainPairSerializer):
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    user = TokenUserSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.username_field in self.fields:
            self.fields[self.username_field].write_only = True

    def validate(self, attrs):
        user_model = get_user_model()

        identifier = attrs.get(self.username_field)
        password = attrs.get("password")

        if not identifier or not password:
            raise AuthenticationFailed(
                _("Please provide credentials."),
                code="missing_credentials",
            )

        if not user_model._default_manager.filter(
            **{self.username_field: identifier}
        ).exists():
            raise AuthenticationFailed(_("User not found."), code="user_not_found")

        user = authenticate(
            request=self.context.get("request"),
            **{self.username_field: identifier, "password": password},
        )
        if user is None:
            raise AuthenticationFailed(
                _("Invalid credentials."),
                code="invalid_credentials",
            )

        refresh = self.get_token(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": TokenUserSerializer(user, context=self.context).data,
        }


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(
        max_length=EMAIL_VERIFICATION_CODE_LENGTH,
        min_length=EMAIL_VERIFICATION_CODE_LENGTH,
        required=True,
        help_text=f"{EMAIL_VERIFICATION_CODE_LENGTH}-digit OTP code",
    )

    def validate(self, data):
        if not verify_code(data["email"], data["code"]):
            raise serializers.ValidationError({"code": "Invalid or expired code"})
        return data


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
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()

        if not is_email_verified_for_registration(email):
            raise serializers.ValidationError(
                _("Email is not verified."),
                code="email_not_verified",
            )

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                _("User already exists."),
                code="email_already_registered",
            )

        return email

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": [_("Passwords do not match.")]},
                code="passwords_do_not_match",
            )

        try:
            validate_password(password=password, user=None)
        except DjangoValidationError as e:
            raise serializers.ValidationError(
                {"password": e.messages},
                code="password_invalid",
            )

        return attrs


class RegisterBrokerSerializer(FileSizeValidationMixin, BaseRegisterSerializer):
    inn = serializers.FileField(required=True)
    inn_number = serializers.CharField(required=True, max_length=12)
    passport = serializers.FileField(required=True)

    def validate_inn(self, file):
        return self._validate_file_size(file, "inn")

    def validate_inn_number(self, value: str) -> str:
        value = str(value).strip()
        validate_inn(value)
        return value

    def validate_passport(self, file):
        return self._validate_file_size(file, "passport")


class BrokerInfoSerializer(serializers.ModelSerializer):
    inn_number = serializers.CharField(source="user.inn_number", read_only=True)

    class Meta:
        model = Broker
        fields = [
            "id",
            "is_verified",
            "verification_status",
            "verified_at",
            "rejected_at",
            "rejection_reason",
            "inn_number",
        ]


class RegisterDeveloperSerializer(BaseRegisterSerializer):
    company_name = serializers.CharField(required=True)


class DeveloperInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Developer
        fields = ["company_name"]


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


class MeSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()
    developer = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "is_broker",
            "is_developer",
            "is_admin",
            "broker",
            "developer",
            "documents",
        )

    def get_broker(self, obj):
        broker = getattr(obj, "broker", None)
        if not broker:
            return None
        return BrokerInfoSerializer(broker, context=self.context).data

    def get_developer(self, obj):
        developer = getattr(obj, "developer", None)
        if not developer:
            return None
        return DeveloperInfoSerializer(developer, context=self.context).data

    def get_documents(self, obj):
        if obj.role == User.Roles.ADMIN:
            return []
        return UserDocumentSerializer(
            obj.documents.all(),
            many=True,
            context=self.context,
        ).data


class UserDocumentsUploadSerializer(FileSizeValidationMixin, serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=UserDocument.Types.choices)
    document = serializers.FileField(required=True)
    document_name = serializers.CharField(
        required=False, allow_blank=False, max_length=255
    )

    def validate_document(self, file):
        return self._validate_file_size(file, "document")

    def validate(self, attrs):
        user = self.context["request"].user
        doc_type = attrs["doc_type"]

        if user.role == User.Roles.ADMIN:
            raise serializers.ValidationError(
                {"error": _("Админ не может загружать документы.")}
            )

        if (
            doc_type in {UserDocument.Types.INN, UserDocument.Types.PASSPORT}
            and user.documents.filter(doc_type=doc_type).exists()
        ):
            raise serializers.ValidationError(
                {"doc_type": _("Документ этого типа уже загружен.")}
            )

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        document = self.validated_data["document"]
        document_name = (
            self.validated_data.get("document_name")
            or os.path.splitext(document.name)[0]
        )

        return UserDocument.objects.create(
            user=user,
            doc_type=self.validated_data["doc_type"],
            document=document,
            document_name=document_name,
        )


class UserDocumentNameUpdateSerializer(serializers.Serializer):
    document_id = serializers.IntegerField(required=True)
    document_name = serializers.CharField(
        required=True, allow_blank=False, max_length=255
    )

    def validate(self, attrs):
        user = self.context["request"].user

        if user.role == User.Roles.ADMIN:
            raise serializers.ValidationError(
                {"error": _("Админ не может изменять документы.")}
            )

        try:
            document = user.documents.get(id=attrs["document_id"])
        except UserDocument.DoesNotExist:
            raise serializers.ValidationError({"document_id": _("Документ не найден.")})

        attrs["document_obj"] = document
        return attrs

    def save(self, **kwargs):
        document = self.validated_data["document_obj"]
        document.document_name = self.validated_data["document_name"]
        document.save(update_fields=["document_name", "updated_at"])
        return document
