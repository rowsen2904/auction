# apps/auctions/services/rules.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction, Bid
from auctions.participants import is_participant
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

User = get_user_model()


@dataclass(frozen=True)
class Ctx:
    auction: Auction
    user: User
    now: timezone.datetime


def ctx_for(*, auction: Auction, user) -> Ctx:
    return Ctx(auction=auction, user=user, now=timezone.now())


def is_admin(user) -> bool:
    return bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    )


def ensure_mode(ctx: Ctx, *, allowed: set[str], message: str) -> None:
    if ctx.auction.mode not in allowed:
        raise ValidationError({"detail": message})


def ensure_active_window(ctx: Ctx) -> None:
    if ctx.auction.status != Auction.Status.ACTIVE:
        raise ValidationError({"detail": "Auction is not active."})
    if not (ctx.auction.start_date <= ctx.now < ctx.auction.end_date):
        raise ValidationError({"detail": "Auction is not within active time window."})


def ensure_not_owner(ctx: Ctx) -> None:
    if ctx.user.id == ctx.auction.owner_id:
        raise ValidationError({"detail": "Owner cannot bid on their own auction."})


def ensure_min_price(ctx: Ctx, *, amount: Decimal) -> None:
    if amount < ctx.auction.min_price:
        raise ValidationError({"detail": "Bid amount is below min_price."})


def ensure_joined(*, auction_id: int, user_id: int) -> None:
    if not is_participant(auction_id=auction_id, user_id=user_id):
        raise ValidationError({"detail": "You must join the auction before bidding."})


def ensure_not_current_leader(*, auction: Auction, user_id: int) -> None:
    if not auction.highest_bid_id:
        return
    leader_id = (
        Bid.objects.filter(id=auction.highest_bid_id)
        .values_list("broker_id", flat=True)
        .first()
    )
    if leader_id == user_id:
        raise ValidationError({"detail": "You are already the highest bidder."})


def ensure_can_cancel(*, auction: Auction, user) -> None:
    now = timezone.now()

    if now >= auction.start_date:
        raise ValidationError(
            {"detail": "Auction cannot be cancelled after it has started."}
        )

    lock_window = getattr(
        settings, "AUCTION_CANCEL_LOCK_BEFORE_START", timedelta(minutes=10)
    )
    if (auction.start_date - now) <= lock_window and not is_admin(user):
        raise PermissionDenied("Only admin can cancel an auction close to its start.")


def open_compute_amount(*, auction: Auction, requested: Decimal) -> Decimal:
    """
    OPEN rules:
    - First bid always equals min_price (ignore requested).
    - Afterwards: requested must be >= current_price + OPEN_BID_MIN_INCREMENT.
    """
    if auction.bids_count == 0 or auction.current_price <= Decimal("0.00"):
        return auction.min_price

    step = getattr(settings, "OPEN_BID_MIN_INCREMENT", Decimal("150000.00"))
    min_allowed = auction.current_price + step
    if requested < min_allowed:
        raise ValidationError({"detail": f"Bid must be at least {min_allowed}."})
    return requested
