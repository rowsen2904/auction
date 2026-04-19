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


def broker_payout_receipt_upload_to(instance: "DealSettlement", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    sid = instance.id or "tmp"
    return f"settlements/{sid}/broker_payout/{uuid4().hex}.{ext}"


def developer_receipt_upload_to(instance: "DealSettlement", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    sid = instance.id or "tmp"
    return f"settlements/{sid}/developer/{uuid4().hex}.{ext}"


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


class DealSettlement(models.Model):
    """
    Транзитный расчёт по одной сделке.

    Флоу:
      1. Сделка подтверждена (Deal.status=CONFIRMED) → создаётся Settlement.
      2. Платформа платит брокеру `broker_amount` (x%). Админ фиксирует
         факт в платформе, загружая чек. paid_to_broker=True.
         Дедлайн: broker_payout_deadline = created_at + 3 дня.
      3. Девелопер обязан в течение 6 месяцев перевести платформе
         total_from_developer = broker_amount + platform_amount. Девелопер
         загружает чек (developer_receipt), админ подтверждает поступление
         (received_from_developer=True).
    Когда оба флага True — сделка "финансово закрыта".
    """

    deal = models.OneToOneField(
        "deals.Deal",
        on_delete=models.PROTECT,
        related_name="settlement",
    )

    # Амоунты — фиксируются в момент создания (snapshot)
    broker_amount = models.DecimalField(
        _("К выплате брокеру"),
        max_digits=14,
        decimal_places=2,
    )
    broker_rate = models.DecimalField(
        _("Ставка брокера (%)"),
        max_digits=5,
        decimal_places=2,
    )
    platform_amount = models.DecimalField(
        _("Комиссия платформы"),
        max_digits=14,
        decimal_places=2,
    )
    platform_rate = models.DecimalField(
        _("Ставка платформы (%)"),
        max_digits=5,
        decimal_places=2,
    )
    total_from_developer = models.DecimalField(
        _("Долг девелопера"),
        max_digits=14,
        decimal_places=2,
        help_text=_("broker_amount + platform_amount"),
    )

    # Этап 1: платформа → брокеру
    paid_to_broker = models.BooleanField(default=False, db_index=True)
    paid_to_broker_at = models.DateTimeField(null=True, blank=True)
    broker_payout_receipt = models.FileField(
        _("Чек выплаты брокеру"),
        upload_to=broker_payout_receipt_upload_to,
        null=True,
        blank=True,
    )
    broker_payout_deadline = models.DateTimeField(db_index=True)

    # Этап 2: девелопер → платформе
    received_from_developer = models.BooleanField(default=False, db_index=True)
    received_from_developer_at = models.DateTimeField(null=True, blank=True)
    developer_receipt = models.FileField(
        _("Чек девелопера"),
        upload_to=developer_receipt_upload_to,
        null=True,
        blank=True,
    )
    developer_receipt_uploaded_at = models.DateTimeField(null=True, blank=True)
    developer_payment_deadline = models.DateTimeField(db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Расчёт по сделке")
        verbose_name_plural = _("Расчёты по сделкам")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Settlement #{self.id} deal={self.deal_id}"

    @property
    def is_financially_closed(self) -> bool:
        return self.paid_to_broker and self.received_from_developer

    @property
    def broker_payout_overdue(self) -> bool:
        if self.paid_to_broker:
            return False
        return timezone.now() > self.broker_payout_deadline

    @property
    def developer_payment_overdue(self) -> bool:
        if self.received_from_developer:
            return False
        return timezone.now() > self.developer_payment_deadline
