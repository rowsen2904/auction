from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
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

    # OPEN auction only. For CLOSED lot this stays null.
    real_property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="open_auctions",
        null=True,
        blank=True,
    )

    # CLOSED/LOT support (also can mirror OPEN single property for unified reads)
    properties = models.ManyToManyField(
        "properties.Property",
        through="AuctionProperty",
        related_name="lot_auctions",
        blank=True,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_auctions",
    )

    mode = models.CharField(max_length=10, choices=Mode.choices, db_index=True)

    # Minimum acceptable bid amount FOR WHOLE LOT
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

    bids_count = models.PositiveIntegerField(default=0)

    current_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
    )

    highest_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_highest_for_auctions",
    )

    # OPEN only
    winner_bid = models.ForeignKey(
        "Bid",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_winner_for_auctions",
    )

    # Reuse this for CLOSED selected winners
    shortlisted_bids = models.ManyToManyField(
        "auctions.Bid",
        blank=True,
        related_name="shortlisted_in_auctions",
    )

    min_bid_increment = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1.00"))],
        help_text="Минимальный шаг повышения ставки для open-аукциона.",
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
            models.Index(fields=["owner", "-created_at"], name="auc_owner_created_idx"),
            models.Index(
                fields=["real_property", "-created_at"],
                name="auc_open_prop_created_idx",
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
            models.CheckConstraint(
                check=(
                    (
                        Q(mode="open")
                        & Q(min_bid_increment__isnull=False)
                        & Q(min_bid_increment__gte=Decimal("1.00"))
                        & Q(real_property__isnull=False)
                    )
                    | (Q(mode="closed") & Q(min_bid_increment__isnull=True))
                ),
                name="auc_open_requires_increment_and_property",
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

    @property
    def lot_total_price(self) -> Decimal:
        total = self.properties.aggregate(total=Sum("price"))["total"]
        return total or Decimal("0.00")

    def get_single_property(self):
        if self.real_property_id:
            return self.real_property
        return self.properties.order_by("id").first()

    def clean(self):
        super().clean()

        if self.mode == self.Mode.OPEN:
            if self.min_bid_increment is None:
                raise ValidationError(
                    {
                        "min_bid_increment": "Для открытого аукциона укажите "
                        "минимальный шаг ставки."
                    }
                )
            if self.min_bid_increment < Decimal("1.00"):
                raise ValidationError(
                    {
                        "min_bid_increment": "Минимальный шаг ставки должен быть не меньше 1."
                    }
                )
            if self.real_property_id is None:
                raise ValidationError(
                    {"real_property": "Для открытого аукциона требуется один объект."}
                )

        if self.mode == self.Mode.CLOSED:
            self.min_bid_increment = None
            self.real_property = None


class AuctionProperty(models.Model):
    auction = models.ForeignKey(
        Auction,
        on_delete=models.CASCADE,
        related_name="auction_properties",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="auction_links",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "auction_properties"
        constraints = [
            models.UniqueConstraint(
                fields=["auction", "property"],
                name="aucprop_unique_auction_property",
            ),
        ]
        indexes = [
            models.Index(fields=["auction", "property"], name="aucprop_auc_prop_idx"),
            models.Index(fields=["property"], name="aucprop_prop_idx"),
        ]

    def __str__(self) -> str:
        return f"AuctionProperty auction={self.auction_id} property={self.property_id}"


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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # last bids for open auctions and general history
            models.Index(fields=["auction", "-created_at"], name="bid_auc_created_idx"),
            # compute highest quickly (and for admin checks/recalc)
            models.Index(fields=["auction", "-amount"], name="bid_auc_amount_idx"),
            models.Index(
                fields=["broker", "-created_at"], name="bid_broker_created_idx"
            ),
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
            # One open bid per broker per auction
            models.UniqueConstraint(
                fields=["auction", "broker"],
                condition=Q(is_sealed=False),
                name="bid_unique_open_per_broker_per_auction",
            ),
        ]

    def __str__(self) -> str:
        return f"Bid #{self.id} auction={self.auction_id} amount={self.amount}"
