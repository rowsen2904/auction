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


class UnifiedDocumentSerializer(serializers.Serializer):
    """Unified serializer for both user documents and deal documents."""

    id = serializers.IntegerField()
    source = serializers.CharField()  # "user" | "deal"
    doc_type = serializers.CharField()
    document_name = serializers.CharField()
    url = serializers.CharField()
    filename = serializers.CharField()
    extension = serializers.CharField()
    created_at = serializers.DateTimeField()
    # Deal-specific fields (null for user documents)
    deal_id = serializers.IntegerField(allow_null=True)
    deal_status = serializers.CharField(allow_null=True)
    property_address = serializers.CharField(allow_null=True)


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
            raise serializers.ValidationError({"code": _("Неверный или истекший код.")})
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
                _("Email не подтверждён."),
                code="email_not_verified",
            )

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                _("Пользователь уже существует."),
                code="email_already_registered",
            )

        return email

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": [_("Пароли не совпадают.")]},
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
    phone_number = serializers.CharField(required=False, max_length=20, default="")
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
            "phone_number",
        ]


class DeveloperInfoSerializer(serializers.ModelSerializer):
    inn_number = serializers.CharField(source="user.inn_number", read_only=True)

    class Meta:
        model = Developer
        fields = ["company_name", "phone_number", "inn_number"]


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


class UserDocumentAccessMixin:
    def get_user_document(self, document_id):
        user = self.context["request"].user

        if user.role == User.Roles.ADMIN:
            raise serializers.ValidationError(
                {"error": _("Админ не может управлять документами.")}
            )

        try:
            return user.documents.get(id=document_id)
        except UserDocument.DoesNotExist:
            raise serializers.ValidationError({"document_id": _("Документ не найден.")})


class UserDocumentNameUpdateSerializer(UserDocumentAccessMixin, serializers.Serializer):
    document_id = serializers.IntegerField(required=True)
    document_name = serializers.CharField(
        required=True, allow_blank=False, max_length=255
    )

    def validate(self, attrs):
        attrs["document_obj"] = self.get_user_document(attrs["document_id"])
        return attrs

    def save(self, **kwargs):
        document = self.validated_data["document_obj"]
        document.document_name = self.validated_data["document_name"]
        document.save(update_fields=["document_name", "updated_at"])
        return document


class UserDocumentDeleteSerializer(UserDocumentAccessMixin, serializers.Serializer):
    document_id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        attrs["document_obj"] = self.get_user_document(attrs["document_id"])
        return attrs

    def save(self, **kwargs):
        document = self.validated_data["document_obj"]
        document.delete()
        return document


class UserProfileUpdateSerializer(serializers.Serializer):
    """
    Universal profile update payload used both by self-update
    (PATCH /users/me/) and admin-update (PATCH /admin/users/{pk}/).

    Role-specific fields are silently ignored if the target user doesn't have
    the corresponding nested model (e.g. company_name for a broker).
    """

    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    email = serializers.EmailField(required=False)
    inn_number = serializers.CharField(required=False, allow_blank=False, max_length=12)

    phone_number = serializers.CharField(
        required=False, allow_blank=True, max_length=20
    )

    company_name = serializers.CharField(
        required=False, allow_blank=False, max_length=55
    )

    def __init__(self, *args, **kwargs):
        self._is_admin_update = kwargs.pop("is_admin_update", False)
        super().__init__(*args, **kwargs)
        if self._is_admin_update:
            self.fields["is_active"] = serializers.BooleanField(required=False)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        user_id = self.context.get("user_id")
        qs = User.objects.filter(email=email)
        if user_id is not None:
            qs = qs.exclude(id=user_id)
        if qs.exists():
            raise serializers.ValidationError(
                _("Пользователь с таким email уже существует.")
            )
        return email

    def validate_inn_number(self, value: str) -> str:
        value = str(value).strip()
        validate_inn(value)
        user_id = self.context.get("user_id")
        qs = User.objects.filter(inn_number=value)
        if user_id is not None:
            qs = qs.exclude(id=user_id)
        if qs.exists():
            raise serializers.ValidationError(
                _("Пользователь с таким ИНН уже существует.")
            )
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                {"detail": _("Передайте хотя бы одно поле для обновления.")}
            )
        return attrs

    def apply(self, user):
        validated = self.validated_data
        user_fields = []
        for field in ("email", "first_name", "last_name", "inn_number"):
            if field in validated and getattr(user, field) != validated[field]:
                setattr(user, field, validated[field])
                user_fields.append(field)

        if self._is_admin_update and "is_active" in validated:
            if user.is_active != validated["is_active"]:
                user.is_active = validated["is_active"]
                user_fields.append("is_active")

        if user_fields:
            user.save(update_fields=user_fields)

        broker = getattr(user, "broker", None)
        if broker is not None and "phone_number" in validated:
            if broker.phone_number != validated["phone_number"]:
                broker.phone_number = validated["phone_number"]
                broker.save(update_fields=["phone_number"])

        developer = getattr(user, "developer", None)
        if developer is not None and "company_name" in validated:
            if developer.company_name != validated["company_name"]:
                developer.company_name = validated["company_name"]
                developer.save(update_fields=["company_name"])

        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        required=True,
        style={"input_type": "password"},
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        required=True,
        style={"input_type": "password"},
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Старый пароль введён неверно."))
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        new_password = attrs.get("new_password")
        new_password_confirm = attrs.get("new_password_confirm")

        if new_password != new_password_confirm:
            raise serializers.ValidationError(
                {"new_password_confirm": [_("Пароли не совпадают.")]},
                code="passwords_do_not_match",
            )

        try:
            validate_password(password=new_password, user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(
                {"new_password": e.messages},
                code="password_invalid",
            )

        if attrs["old_password"] == new_password:
            raise serializers.ValidationError(
                {"new_password": [_("Новый пароль должен отличаться от старого.")]},
                code="same_as_old_password",
            )

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
