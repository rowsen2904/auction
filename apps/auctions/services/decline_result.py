from __future__ import annotations

from auctions.models import Auction, Bid
from deals.models import Deal, DealLog
from django.db import transaction
from django.utils import timezone
from notifications.services import (
    notify_auction_result_rejected,
    notify_auction_winner_declined,
    notify_auction_winner_promoted,
)
from rest_framework.exceptions import ValidationError

DECLINABLE_DEAL_STATUSES = {
    Deal.Status.PENDING_DOCUMENTS,
}


def _assert_can_decline(auction: Auction) -> None:
    if auction.status not in {Auction.Status.FINISHED}:
        raise ValidationError(
            {"detail": "Отказ от результата возможен только после завершения аукциона."}
        )
    if auction.winner_bid_id is None:
        raise ValidationError({"detail": "Нет текущего победителя для отказа."})


def _find_next_candidate(auction: Auction) -> Bid | None:
    excluded_ids = list(auction.declined_bids.values_list("id", flat=True))

    if auction.mode == Auction.Mode.OPEN:
        return (
            Bid.objects.filter(auction_id=auction.id, is_sealed=False)
            .exclude(id__in=excluded_ids)
            .select_related("broker")
            .order_by("-amount", "created_at")
            .first()
        )

    shortlisted_ids = set(auction.shortlisted_bids.values_list("id", flat=True))
    pool = Bid.objects.filter(auction_id=auction.id, is_sealed=True).exclude(
        id__in=excluded_ids
    )
    if shortlisted_ids:
        remaining_shortlist = pool.filter(id__in=shortlisted_ids)
        if remaining_shortlist.exists():
            pool = remaining_shortlist
    return pool.select_related("broker").order_by("-amount", "created_at").first()


def _decline_active_deals(auction: Auction, declined_bid: Bid, reason: str) -> None:
    deals_qs = Deal.objects.select_for_update().filter(
        auction_id=auction.id, bid_id=declined_bid.id
    )
    for deal in deals_qs:
        if deal.status not in DECLINABLE_DEAL_STATUSES:
            raise ValidationError(
                {
                    "detail": (
                        f"Нельзя отказаться от результата: сделка #{deal.id} "
                        f"уже в статусе {deal.get_status_display()}."
                    )
                }
            )
        deal.status = Deal.Status.DECLINED
        deal.save(update_fields=["status", "updated_at"])
        DealLog.objects.create(
            deal=deal,
            action=DealLog.Action.MARKED_DECLINED,
            detail=(
                f"Сделка отменена: девелопер отказался от результата аукциона. "
                f"Причина: {reason}"
            ),
        )


def decline_auction_result(*, auction: Auction, reason: str) -> dict:
    _assert_can_decline(auction)

    if not reason or not reason.strip():
        raise ValidationError({"reason": "Причина обязательна."})

    declined_bid = Bid.objects.select_related("broker").get(id=auction.winner_bid_id)

    with transaction.atomic():
        _decline_active_deals(auction, declined_bid, reason)

        auction.declined_bids.add(declined_bid)
        auction.shortlisted_bids.remove(declined_bid)

        next_bid = _find_next_candidate(auction)

        if next_bid is not None:
            auction.winner_bid = next_bid
            auction.owner_decision = Auction.OwnerDecision.PENDING
            auction.owner_decided_at = None
            auction.owner_rejection_reason = ""
            auction.save(
                update_fields=[
                    "winner_bid_id",
                    "owner_decision",
                    "owner_decided_at",
                    "owner_rejection_reason",
                    "updated_at",
                ]
            )
            if auction.mode == Auction.Mode.CLOSED:
                auction.shortlisted_bids.add(next_bid)
        else:
            auction.winner_bid = None
            auction.owner_decision = Auction.OwnerDecision.REJECTED
            auction.owner_decided_at = timezone.now()
            auction.owner_rejection_reason = reason
            auction.status = Auction.Status.FAILED
            auction.save(
                update_fields=[
                    "winner_bid_id",
                    "owner_decision",
                    "owner_decided_at",
                    "owner_rejection_reason",
                    "status",
                    "updated_at",
                ]
            )

    notify_auction_winner_declined(
        auction=auction, declined_bid=declined_bid, reason=reason
    )

    if next_bid is not None:
        notify_auction_winner_promoted(auction=auction, new_winner_bid=next_bid)
        return {
            "auction_failed": False,
            "new_winner_bid_id": next_bid.id,
        }

    notify_auction_result_rejected(
        auction=auction, winner_bid=declined_bid, reason=reason
    )
    return {"auction_failed": True, "new_winner_bid_id": None}
