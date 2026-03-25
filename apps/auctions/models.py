# apps/auctions/models.py
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
        SCHEDULED = "scheduled", "Scheduled"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    # Property being auctioned
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
        default=Status.SCHEDULED,
        db_index=True,
    )

    # Denormalized counters for fast reads
    bids_count = models.PositiveIntegerField(default=0)

    # Cached current highest amount (OPEN auctions live, CLOSED optional)
    current_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
    )

    # Highest bid pointer (mainly OPEN)
    highest_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_highest_for_auctions",
    )

    # Winner bid pointer (OPEN: auto highest at finish; CLOSED: may be set later/manual)
    winner_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_winner_for_auctions",
    )

    shortlisted_bids = models.ManyToManyField(
        "auctions.Bid",
        blank=True,
        related_name="shortlisted_in_auctions",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # list/filter + background finishing queries
            models.Index(fields=["status", "end_date"], name="auc_status_end_idx"),
            models.Index(
                fields=["mode", "status", "end_date"], name="auc_mode_status_end_idx"
            ),
            models.Index(
                fields=["real_property", "-created_at"], name="auc_prop_created_idx"
            ),
            # optional but often useful when listing my auctions / sorting
            models.Index(fields=["owner", "-created_at"], name="auc_owner_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["real_property"],
                name="unique_auction_per_property",
            ),
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

    # Marks bids that belong to SEALED/CLOSED auctions (one bid per broker per auction)
    # This allows a partial unique constraint for sealed only.
    is_sealed = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # last bids for open auctions and general history
            models.Index(fields=["auction", "-created_at"], name="bid_auc_created_idx"),
            # compute highest quickly (and for admin checks/recalc)
            models.Index(fields=["auction", "-amount"], name="bid_auc_amount_idx"),
            # broker history
            models.Index(
                fields=["broker", "-created_at"], name="bid_broker_created_idx"
            ),
            # fast existence checks / joins for sealed logic (optional but practical)
            models.Index(fields=["auction", "broker"], name="bid_auc_broker_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=Decimal("0.00")),
                name="bid_amount_gt_0",
            ),
            # One sealed bid per broker per auction (Postgres will create a partial unique index)
            models.UniqueConstraint(
                fields=["auction", "broker"],
                condition=Q(is_sealed=True),
                name="bid_unique_sealed_per_broker_per_auction",
            ),
        ]

    def __str__(self) -> str:
        return f"Bid #{self.id} auction={self.auction_id} amount={self.amount}"
