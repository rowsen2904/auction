from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def deal_document_upload_to(instance: "Deal", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    deal_id = instance.id or "tmp"
    return f"deals/{deal_id}/{uuid4().hex}.{ext}"


class Deal(models.Model):
    class Status(models.TextChoices):
        PENDING_DOCUMENTS = "pending_documents", _("Pending Documents")
        ADMIN_REVIEW = "admin_review", _("Admin Review")
        DEVELOPER_CONFIRM = "developer_confirm", _("Developer Confirm")
        CONFIRMED = "confirmed", _("Confirmed")

    class ObligationStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        FULFILLED = "fulfilled", _("Fulfilled")
        OVERDUE = "overdue", _("Overdue")

    auction = models.ForeignKey(
        "auctions.Auction",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    bid = models.OneToOneField(
        "auctions.Bid",
        on_delete=models.PROTECT,
        related_name="deal",
    )
    broker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="broker_deals",
    )
    developer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="developer_deals",
    )
    real_property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    amount = models.DecimalField(
        _("Сумма ставки"),
        max_digits=14,
        decimal_places=2,
    )

    status = models.CharField(
        _("Статус сделки"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_DOCUMENTS,
        db_index=True,
    )
    obligation_status = models.CharField(
        _("Статус обязательства"),
        max_length=10,
        choices=ObligationStatus.choices,
        default=ObligationStatus.ACTIVE,
        db_index=True,
    )

    # Documents
    ddu_document = models.FileField(
        _("ДДУ"),
        upload_to=deal_document_upload_to,
        null=True,
        blank=True,
    )
    payment_proof_document = models.FileField(
        _("Подтверждение оплаты"),
        upload_to=deal_document_upload_to,
        null=True,
        blank=True,
    )
    broker_comment = models.TextField(
        _("Комментарий брокера"),
        blank=True,
        default="",
    )

    # Rejection reasons (preserved across cycles)
    admin_rejection_reason = models.TextField(
        _("Причина отклонения (админ)"),
        blank=True,
        default="",
    )
    developer_rejection_reason = models.TextField(
        _("Причина отклонения (девелопер)"),
        blank=True,
        default="",
    )

    # Deadline
    document_deadline = models.DateTimeField(
        _("Дедлайн загрузки документов"),
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Сделка")
        verbose_name_plural = _("Сделки")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "-created_at"], name="deal_status_created_idx"
            ),
            models.Index(
                fields=["broker", "-created_at"], name="deal_broker_created_idx"
            ),
            models.Index(
                fields=["developer", "-created_at"], name="deal_dev_created_idx"
            ),
            models.Index(
                fields=["obligation_status", "document_deadline"],
                name="deal_oblig_deadline_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=Decimal("0.00")),
                name="deal_amount_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return f"Deal #{self.id} (auction={self.auction_id}, broker={self.broker_id})"


class DealLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", _("Created")
        DDU_UPLOADED = "ddu_uploaded", _("DDU Uploaded")
        PAYMENT_PROOF_UPLOADED = "payment_proof_uploaded", _("Payment Proof Uploaded")
        COMMENT_ADDED = "comment_added", _("Comment Added")
        SUBMITTED_FOR_REVIEW = "submitted_for_review", _("Submitted for Review")
        ADMIN_APPROVED = "admin_approved", _("Admin Approved")
        ADMIN_REJECTED = "admin_rejected", _("Admin Rejected")
        DEVELOPER_CONFIRMED = "developer_confirmed", _("Developer Confirmed")
        DEVELOPER_REJECTED = "developer_rejected", _("Developer Rejected")
        MARKED_OVERDUE = "marked_overdue", _("Marked Overdue")

    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    action = models.CharField(
        max_length=30,
        choices=Action.choices,
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("Лог сделки")
        verbose_name_plural = _("Логи сделок")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["deal", "-created_at"], name="deallog_deal_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"DealLog #{self.id} [{self.action}] deal={self.deal_id}"
