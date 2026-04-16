from __future__ import annotations

from auctions.models import Auction, Bid
from deals.models import Deal
from deals.services import create_deal_from_bid
from django.db import transaction
from django.utils import timezone
from notifications.services import (
    notify_auction_result_confirmed,
    notify_auction_result_rejected,
    notify_closed_not_selected,
)
from properties.models import Property
from rest_framework.exceptions import ValidationError


def _ensure_can_decide(auction: Auction) -> None:
    if auction.status != Auction.Status.FINISHED:
        raise ValidationError(
            {
                "detail": "Решение по результату доступно только после завершения аукциона."
            }
        )
    if auction.owner_decision != Auction.OwnerDecision.PENDING:
        raise ValidationError({"detail": "По этому аукциону уже принято решение."})


def _winner_bid(auction: Auction) -> Bid | None:
    if not auction.winner_bid_id:
        return None
    return Bid.objects.select_related("broker").filter(id=auction.winner_bid_id).first()


def confirm_auction_result(*, auction: Auction) -> list[Deal]:
    _ensure_can_decide(auction)

    winner = _winner_bid(auction)
    if winner is None:
        raise ValidationError(
            {
                "detail": "Нет победителя для подтверждения — результат подтвердить нельзя."
            }
        )

    created_deals: list[Deal] = []

    with transaction.atomic():
        if auction.mode == Auction.Mode.OPEN:
            prop = None
            if auction.real_property_id:
                prop = Property.objects.filter(id=auction.real_property_id).first()
            if prop is None:
                prop = auction.properties.order_by("id").first()
            if prop is None:
                raise ValidationError({"detail": "Нет объекта для сделки."})
            props = [prop]
        else:
            props = list(auction.properties.all().only("id", "price"))
            if not props:
                raise ValidationError({"detail": "В лоте нет объектов."})

        for prop in props:
            if Deal.objects.filter(
                auction_id=auction.id, real_property_id=prop.id
            ).exists():
                continue
            deal = create_deal_from_bid(
                auction=auction,
                bid=winner,
                real_property=prop,
            )
            created_deals.append(deal)

        auction.owner_decision = Auction.OwnerDecision.CONFIRMED
        auction.owner_decided_at = timezone.now()
        auction.owner_rejection_reason = ""
        auction.save(
            update_fields=[
                "owner_decision",
                "owner_decided_at",
                "owner_rejection_reason",
                "updated_at",
            ]
        )

    if auction.mode == Auction.Mode.CLOSED:
        notify_closed_not_selected(
            auction=auction, selected_broker_ids=[winner.broker_id]
        )
    notify_auction_result_confirmed(auction=auction, winner_bid=winner)

    return created_deals


def reject_auction_result(*, auction: Auction, reason: str) -> None:
    _ensure_can_decide(auction)

    winner = _winner_bid(auction)

    with transaction.atomic():
        auction.owner_decision = Auction.OwnerDecision.REJECTED
        auction.owner_decided_at = timezone.now()
        auction.owner_rejection_reason = reason
        auction.status = Auction.Status.FAILED
        auction.save(
            update_fields=[
                "owner_decision",
                "owner_decided_at",
                "owner_rejection_reason",
                "status",
                "updated_at",
            ]
        )

    notify_auction_result_rejected(auction=auction, winner_bid=winner, reason=reason)
