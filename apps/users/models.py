import os
from uuid import uuid4

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from helpers.encrypted_fields import EncryptedCharField

from .validators import validate_inn


def user_document_folder(instance, filename):
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    user_id = instance.user_id or "tmp"
    return f"users/{user_id}/documents/{uuid4().hex}{ext}"


def developer_ddu_template_folder(instance, filename):
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    user_id = instance.user_id or "tmp"
    return f"developers/{user_id}/ddu_template/{uuid4().hex}{ext}"


# TODO must remove
def broker_passport_folder():
    pass


def broker_inn_folder():
    pass


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Roles.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class UserDocumentQuerySet(models.QuerySet):
    def for_user(self, user):
        user_id = getattr(user, "pk", user)
        return self.filter(user_id=user_id)

    def inn(self):
        return self.filter(doc_type=UserDocument.Types.INN)

    def passports(self):
        return self.filter(doc_type=UserDocument.Types.PASSPORT)

    def others(self):
        return self.filter(doc_type=UserDocument.Types.OTHERS)


class User(AbstractBaseUser, PermissionsMixin):
    class Roles(models.TextChoices):
        DEVELOPER = "developer", _("Developer")
        BROKER = "broker", _("Broker")
        ADMIN = "admin", _("Admin")

    email = models.EmailField(_("email address"), unique=True)

    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Roles.choices,
        default=Roles.DEVELOPER,
        db_index=True,
    )
    inn_number = models.CharField(
        max_length=12, validators=[validate_inn], blank=True, null=True, unique=True
    )

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now, db_index=True)

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["role", "is_active"]),
        ]

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_developer(self):
        return self.role == self.Roles.DEVELOPER

    @property
    def is_broker(self):
        return self.role == self.Roles.BROKER

    @property
    def is_admin(self):
        return self.role == self.Roles.ADMIN


class Broker(models.Model):
    class VerificationStatuses(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="broker")

    phone_number = EncryptedCharField(
        _("phone number"),
        max_length=128,
        blank=True,
        default="",
    )

    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(
        _("rejection reason"),
        max_length=1000,
        null=True,
        blank=True,
    )
    verification_status = models.CharField(
        _("verification status"),
        max_length=20,
        choices=VerificationStatuses.choices,
        default=VerificationStatuses.PENDING,
        db_index=True,
    )

    class Meta:
        verbose_name = _("broker")
        verbose_name_plural = _("brokers")
        indexes = [
            models.Index(fields=["is_verified", "verified_at"]),
        ]

    def __str__(self):
        return "{}".format(self.user.get_full_name())

    def save(self, *args, **kwargs):
        if self.user.role != User.Roles.BROKER:
            self.user.role = User.Roles.BROKER
            self.user.save(update_fields=["role"])
        super().save(*args, **kwargs)

    def verify_broker(self):
        should_update = (
            self.verification_status != self.VerificationStatuses.ACCEPTED
            or self.is_verified is False
            or self.verified_at is None
            or self.rejected_at is not None
            or self.rejection_reason is not None
        )
        if not should_update:
            return

        self.verification_status = self.VerificationStatuses.ACCEPTED
        self.is_verified = True
        self.verified_at = timezone.now()
        self.rejected_at = None
        self.rejection_reason = None
        self.save(
            update_fields=[
                "verification_status",
                "is_verified",
                "verified_at",
                "rejected_at",
                "rejection_reason",
            ]
        )

    def set_as_rejected(self, reason: str):
        reason = (reason or "").strip()

        self.verification_status = self.VerificationStatuses.REJECTED
        self.is_verified = False
        self.rejected_at = timezone.now()
        self.verified_at = None
        self.rejection_reason = reason
        self.save(
            update_fields=[
                "verification_status",
                "is_verified",
                "verified_at",
                "rejected_at",
                "rejection_reason",
            ]
        )


class Developer(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="developer"
    )

    company_name = models.CharField(
        _("company name"),
        max_length=55,
    )

    phone_number = EncryptedCharField(
        _("phone number"),
        max_length=128,
        blank=True,
        default="",
    )

    ddu_template = models.FileField(
        _("Шаблон ДДУ"),
        upload_to=developer_ddu_template_folder,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("developer")
        verbose_name_plural = _("developers")

    def __str__(self):
        return "{}".format(self.user.get_full_name())

    def save(self, *args, **kwargs):
        if self.user.role != User.Roles.DEVELOPER:
            self.user.role = User.Roles.DEVELOPER
            self.user.save(update_fields=["role"])
        super().save(*args, **kwargs)


class UserDocument(models.Model):
    class Types(models.TextChoices):
        INN = "inn", _("ИНН")
        PASSPORT = "passport", _("Паспорт")
        OTHERS = "others", _("Другие")

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document = models.FileField(upload_to=user_document_folder)
    document_name = models.CharField(
        max_length=255,
        blank=True,
    )
    doc_type = models.CharField(
        _("тип документа"),
        max_length=15,
        choices=Types.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserDocumentQuerySet.as_manager()

    class Meta:
        verbose_name = _("документ пользователя")
        verbose_name_plural = _("документы пользователя")
        indexes = [
            models.Index(fields=["user", "doc_type"]),
            models.Index(fields=["user", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "doc_type"],
                condition=Q(doc_type__in=["inn", "passport"]),
                name="uniq_user_single_primary_doc_type",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.document_name or self.filename

    @property
    def filename(self):
        return os.path.basename(self.document.name) if self.document else ""

    @property
    def extension(self):
        return os.path.splitext(self.filename)[1].lower()

    def clean(self):
        if self.user.role == User.Roles.ADMIN:
            raise ValidationError({"user": _("Админ не может загружать документы.")})

    def save(self, *args, **kwargs):
        if not self.document_name and self.document:
            self.document_name = os.path.basename(self.document.name)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        storage = self.document.storage if self.document else None
        name = self.document.name if self.document else None
        super().delete(*args, **kwargs)
        if storage and name:
            storage.delete(name)
