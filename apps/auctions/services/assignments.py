from __future__ import annotations

from auctions.models import Auction, Bid
from deals.models import Deal
from deals.services import create_deal_from_bid
from django.db import transaction
from notifications.services import notify_closed_not_selected
from rest_framework.exceptions import ValidationError


def auto_select_closed_winner(*, auction: Auction) -> Bid | None:
    """
    Automatically select the winner for a finished CLOSED auction.

    Winner = bid with the highest amount.
    Tie-breaker = earliest created_at (first to bid wins).

    Sets auction.winner_bid, auction.shortlisted_bids, and creates deals
    for every property in the lot.
    """
    if auction.mode != Auction.Mode.CLOSED:
        return None

    winner_bid = (
        Bid.objects.filter(auction_id=auction.id, is_sealed=True)
        .select_related("broker")
        .order_by("-amount", "created_at")
        .first()
    )

    if winner_bid is None:
        return None

    with transaction.atomic():
        auction.winner_bid = winner_bid
        auction.save(update_fields=["winner_bid_id", "updated_at"])
        auction.shortlisted_bids.set([winner_bid.id])

        lot_properties = list(auction.properties.all().only("id", "price"))
        for prop in lot_properties:
            if not Deal.objects.filter(
                auction_id=auction.id, real_property_id=prop.id
            ).exists():
                create_deal_from_bid(
                    auction=auction,
                    bid=winner_bid,
                    real_property=prop,
                )

    notify_closed_not_selected(
        auction=auction,
        selected_broker_ids=[winner_bid.broker_id],
    )

    return winner_bid


def select_closed_auction_winner(*, auction: Auction, broker_id: int) -> Bid:
    """
    Manually select a single winner for a finished CLOSED auction.

    Sets auction.winner_bid, auction.shortlisted_bids, and creates deals
    for every property in the lot.
    """
    if auction.mode != Auction.Mode.CLOSED:
        raise ValidationError(
            {"detail": "Выбор победителя доступен только для закрытого аукциона."}
        )

    if auction.status != Auction.Status.FINISHED:
        raise ValidationError(
            {"detail": "Выбирать победителя можно только после завершения аукциона."}
        )

    bid = (
        Bid.objects.filter(
            auction_id=auction.id,
            is_sealed=True,
            broker_id=broker_id,
        )
        .select_related("broker")
        .first()
    )

    if bid is None:
        raise ValidationError(
            {"broker_id": f"Не найдена ставка для брокера: {broker_id}"}
        )

    with transaction.atomic():
        auction.winner_bid = bid
        auction.save(update_fields=["winner_bid_id", "updated_at"])
        auction.shortlisted_bids.set([bid.id])

        lot_properties = list(auction.properties.all().only("id", "price"))
        for prop in lot_properties:
            if not Deal.objects.filter(
                auction_id=auction.id, real_property_id=prop.id
            ).exists():
                create_deal_from_bid(
                    auction=auction,
                    bid=bid,
                    real_property=prop,
                )

    notify_closed_not_selected(
        auction=auction,
        selected_broker_ids=[bid.broker_id],
    )

    return bid
