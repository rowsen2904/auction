import os
from uuid import uuid4

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .validators import validate_inn


def broker_passport_folder(instance, filename):
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    user_id = instance.user_id or "tmp"
    return f"brokers/{user_id}/passports/{uuid4().hex}{ext}"


def broker_inn_folder(instance, filename):
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    user_id = instance.user_id or "tmp"
    return f"brokers/{user_id}/inns/{uuid4().hex}{ext}"


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

    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    inn = models.FileField(upload_to=broker_inn_folder, null=True, blank=True)
    inn_number = models.CharField(max_length=12, validators=[validate_inn], unique=True)
    passport = models.FileField(upload_to=broker_passport_folder, null=True, blank=True)
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
        if not self.verification_status == self.VerificationStatuses.ACCEPTED:
            self.verification_status = self.VerificationStatuses.ACCEPTED
            self.is_verified = True
            self.rejected_at = None
            self.verified_at = timezone.now()
            self.save(
                update_fields=[
                    "verification_status",
                    "is_verified",
                    "verified_at",
                    "rejected_at",
                ]
            )

    def set_as_rejected(self):
        if not self.verification_status == self.VerificationStatuses.REJECTED:
            # Reject broker and reset verification flags if needed
            self.verification_status = self.VerificationStatuses.REJECTED
            self.is_verified = False
            self.rejected_at = timezone.now()
            self.verified_at = None
            self.save(
                update_fields=[
                    "verification_status",
                    "is_verified",
                    "verified_at",
                    "rejected_at",
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
