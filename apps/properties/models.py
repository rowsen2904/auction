from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def property_image_upload_to(instance: "PropertyImage", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    owner_id = instance.property.owner_id or "unknown"
    prop_id = instance.property_id or "tmp"
    return f"developers/{owner_id}/properties/{prop_id}/{uuid4().hex}.{ext}"


class Property(models.Model):
    class PropertyTypes(models.TextChoices):
        APARTMENT = "apartment", _("Apartment")
        HOUSE = "house", _("House")
        TOWNHOUSE = "townhouse", _("Townhouse")
        COMMERCIAL = "commercial", _("Commercial")
        LAND = "land", _("Land")

    class PropertyClasses(models.TextChoices):
        ECONOMY = "economy", _("Economy")
        COMFORT = "comfort", _("Comfort")
        BUSINESS = "business", _("Business")
        PREMIUM = "premium", _("Premium")

    class PropertyStatuses(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")
        SOLD = "sold", _("Sold")

    class ModerationStatuses(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    reference_id = models.UUIDField(
        default=uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="properties",
        db_index=True,
    )

    type = models.CharField(
        _("Тип"),
        max_length=32,
        choices=PropertyTypes.choices,
        db_index=True,
    )

    address = models.CharField(_("Адрес"), max_length=255, db_index=True)

    project = models.CharField(
        _("Проект"),
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    project_comment = models.TextField(
        _("Комментарий к проекту"),
        blank=True,
        default="",
    )

    rooms = models.PositiveSmallIntegerField(
        _("Комнат"),
        null=True,
        blank=True,
        db_index=True,
    )

    purpose = models.CharField(
        _("Назначение"),
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    area = models.DecimalField(
        _("Площадь"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_index=True,
    )

    property_class = models.CharField(
        _("Класс объекта"),
        max_length=32,
        choices=PropertyClasses.choices,
        null=True,
        blank=True,
        db_index=True,
    )

    price = models.DecimalField(
        _("Цена"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        db_index=True,
    )

    commission_rate = models.DecimalField(
        _("Комиссия брокера (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Индивидуальная ставка комиссии застройщика для брокера (%)."),
    )

    deadline = models.DateField(_("Дедлайн"), null=True, blank=True, db_index=True)

    delivery_date = models.DateField(
        _("Дата сдачи"),
        null=True,
        blank=True,
        db_index=True,
    )

    developer_name = models.CharField(
        _("Застройщик"),
        max_length=255,
        blank=True,
        default="",
    )

    floor = models.PositiveSmallIntegerField(
        _("Этаж"),
        null=True,
        blank=True,
    )

    land_number = models.CharField(
        _("Номер участка"),
        max_length=50,
        blank=True,
        default="",
    )

    house_number = models.CharField(
        _("Номер дома"),
        max_length=50,
        blank=True,
        default="",
    )

    status = models.CharField(
        _("Статус"),
        max_length=16,
        choices=PropertyStatuses.choices,
        default=PropertyStatuses.DRAFT,
        db_index=True,
    )
    moderation_status = models.CharField(
        _("Статус модерации"),
        max_length=16,
        choices=ModerationStatuses.choices,
        default=ModerationStatuses.PENDING,
        db_index=True,
    )
    moderation_rejection_reason = models.CharField(
        _("Причина отказа модерации"),
        max_length=1000,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Объект")
        verbose_name_plural = _("Объекты")
        indexes = [
            models.Index(
                fields=["owner", "-created_at"], name="prop_owner_created_idx"
            ),
            models.Index(fields=["type", "price"], name="prop_type_price_idx"),
            models.Index(
                fields=["status", "-created_at"], name="prop_status_created_idx"
            ),
            models.Index(fields=["reference_id"], name="prop_reference_id_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=Q(area__gt=0), name="prop_area_gt_0"),
            models.CheckConstraint(check=Q(price__gte=0), name="prop_price_gte_0"),
            models.CheckConstraint(
                check=(
                    (
                        Q(type="land")
                        & (Q(property_class__isnull=True) | Q(property_class=""))
                    )
                    | (
                        ~Q(type="land")
                        & Q(property_class__isnull=False)
                        & ~Q(property_class="")
                    )
                ),
                name="prop_land_property_class_rule",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} • {self.address}"

    def approve_moderation(self):
        should_update = (
            self.moderation_status != self.ModerationStatuses.APPROVED
            or self.moderation_rejection_reason is not None
        )
        if not should_update:
            return

        self.moderation_status = self.ModerationStatuses.APPROVED
        self.moderation_rejection_reason = None
        self.save(
            update_fields=[
                "moderation_status",
                "moderation_rejection_reason",
                "updated_at",
            ]
        )

    def reject_moderation(self, reason: str):
        reason = (reason or "").strip()

        self.moderation_status = self.ModerationStatuses.REJECTED
        self.moderation_rejection_reason = reason
        self.save(
            update_fields=[
                "moderation_status",
                "moderation_rejection_reason",
                "updated_at",
            ]
        )


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="images",
        db_index=True,
    )

    image = models.ImageField(upload_to=property_image_upload_to, null=True, blank=True)
    external_url = models.URLField(max_length=500, null=True, blank=True)

    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    is_primary = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("property image")
        verbose_name_plural = _("property images")
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["property", "sort_order"], name="pimg_prop_sort_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "sort_order"],
                name="pimg_unique_sort_per_property",
            ),
            models.UniqueConstraint(
                fields=["property"],
                condition=Q(is_primary=True),
                name="pimg_one_primary_per_property",
            ),
            models.CheckConstraint(
                check=Q(image__isnull=False) | Q(external_url__isnull=False),
                name="pimg_requires_image_or_url",
            ),
        ]

    def __str__(self) -> str:
        return f"Image #{self.id} for property {self.property_id}"
