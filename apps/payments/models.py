from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def payment_receipt_upload_to(instance: "Payment", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    payment_id = instance.id or "tmp"
    return f"payments/{payment_id}/{uuid4().hex}.{ext}"


class Payment(models.Model):
    class Type(models.TextChoices):
        DEVELOPER_COMMISSION = "developer_commission", _("Developer Commission")
        PLATFORM_COMMISSION = "platform_commission", _("Platform Commission")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")

    deal = models.ForeignKey(
        "deals.Deal",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    type = models.CharField(
        _("Тип комиссии"),
        max_length=25,
        choices=Type.choices,
        db_index=True,
    )
    amount = models.DecimalField(
        _("Сумма"),
        max_digits=14,
        decimal_places=2,
    )
    rate = models.DecimalField(
        _("Ставка (%)"),
        max_digits=5,
        decimal_places=2,
    )
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    receipt_document = models.FileField(
        _("Чек/квитанция"),
        upload_to=payment_receipt_upload_to,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Выплата")
        verbose_name_plural = _("Выплаты")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["deal", "type"], name="pay_deal_type_idx"),
            models.Index(
                fields=["status", "-created_at"], name="pay_status_created_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gte=Decimal("0.00")),
                name="pay_amount_gte_0",
            ),
            models.UniqueConstraint(
                fields=["deal", "type"],
                name="pay_unique_deal_type",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment #{self.id} [{self.type}] deal={self.deal_id} {self.amount}"
