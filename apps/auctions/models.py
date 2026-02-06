from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Auction(models.Model):
    class Mode(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    # Property being auctioned
    # Named real_property to resolve conflict with property decorator
    real_property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="auctions",
    )

    # Developer who created/owns this auction
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_auctions",
    )

    mode = models.CharField(max_length=10, choices=Mode.choices, db_index=True)

    # Minimum acceptable bid amount
    min_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        db_index=True,
    )

    start_date = models.DateTimeField(db_index=True)
    end_date = models.DateTimeField(db_index=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Denormalized counters for fast reads (avoid COUNT/MAX on every request)
    bids_count = models.PositiveIntegerField(default=0)

    # Cached current highest amount (useful for open auctions and WS updates)
    current_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
    )

    # Points to the highest bid (for open mode real-time)
    highest_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_highest_for_auctions",
    )

    # Selected winner bid (manual for closed / auto for open on finalize)
    winner_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_winner_for_auctions",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "end_date"], name="auc_status_end_idx"),
            models.Index(
                fields=["mode", "status", "end_date"], name="auc_mode_status_end_idx"
            ),
            models.Index(
                fields=["real_property", "-created_at"], name="auc_prop_created_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(end_date__gt=models.F("start_date")),
                name="auc_end_gt_start",
            ),
            models.CheckConstraint(
                check=Q(min_price__gte=Decimal("0.00")),
                name="auc_min_price_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"Auction #{self.id} ({self.mode}, {self.status})"

    @property
    def is_active_now(self) -> bool:
        now = timezone.now()
        return (
            self.status == self.Status.ACTIVE and self.start_date <= now < self.end_date
        )


class Bid(models.Model):
    auction = models.ForeignKey(
        Auction,
        on_delete=models.CASCADE,
        related_name="bids",
    )

    # Broker who placed the bid
    broker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bids",
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["auction", "-created_at"], name="bid_auc_created_idx"),
            models.Index(fields=["auction", "-amount"], name="bid_auc_amount_idx"),
            models.Index(
                fields=["broker", "-created_at"], name="bid_broker_created_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=Decimal("0.00")),
                name="bid_amount_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return f"Bid #{self.id} auction={self.auction_id} amount={self.amount}"
