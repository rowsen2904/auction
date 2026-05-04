from __future__ import annotations

import json
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, PeriodicTask
from notifications.services import (
    notify_auction_failed_no_bids,
    notify_auction_result_awaiting_owner,
    notify_closed_auction_finished_for_owner,
    notify_open_auction_finished_for_owner,
)

from .models import Auction, Bid
from .realtime import broadcast_auction_status

logger = logging.getLogger(__name__)


def _activate_task_name(auction_id: int) -> str:
    return f"auction:{auction_id}:activate"


def _finish_task_name(auction_id: int) -> str:
    return f"auction:{auction_id}:finish"


def cancel_auction_status_tasks(*, auction_id: int) -> None:
    PeriodicTask.objects.filter(
        name__in=[_activate_task_name(auction_id), _finish_task_name(auction_id)]
    ).delete()


def schedule_auction_status_tasks(*, auction_id: int, start_date, end_date) -> None:
    PeriodicTask.objects.filter(
        name__in=[_activate_task_name(auction_id), _finish_task_name(auction_id)]
    ).delete()

    start_clock, _ = ClockedSchedule.objects.get_or_create(clocked_time=start_date)
    end_clock, _ = ClockedSchedule.objects.get_or_create(clocked_time=end_date)

    PeriodicTask.objects.create(
        name=_activate_task_name(auction_id),
        task="auctions.tasks.activate_auction",
        one_off=True,
        enabled=True,
        clocked=start_clock,
        args=json.dumps([auction_id]),
    )
    PeriodicTask.objects.create(
        name=_finish_task_name(auction_id),
        task="auctions.tasks.finish_auction",
        one_off=True,
        enabled=True,
        clocked=end_clock,
        args=json.dumps([auction_id]),
    )


@shared_task(bind=True, ignore_result=True)
def activate_auction(self, auction_id: int) -> None:
    with transaction.atomic():
        auction = Auction.objects.select_for_update().filter(id=auction_id).first()
        if not auction or auction.status != Auction.Status.SCHEDULED:
            return

        now = timezone.now()
        if now < auction.start_date:
            return

        if now >= auction.end_date:
            auction.status = Auction.Status.FINISHED
        else:
            auction.status = Auction.Status.ACTIVE

        auction.save(update_fields=["status", "updated_at"])

        broadcast_auction_status(
            auction_id=auction.id,
            payload={
                "auction": {
                    "id": auction.id,
                    "status": auction.status,
                    "updated_at": auction.updated_at.isoformat(),
                }
            },
        )


def _finalize_auction(auction: Auction) -> None:
    """
    Settle an auction whose end_date has passed: pick a winner if there
    were bids, otherwise mark FAILED. Caller must hold the row lock.
    """
    if auction.mode == Auction.Mode.OPEN:
        bids_count = Bid.objects.filter(
            auction_id=auction.id, is_sealed=False
        ).count()
    else:
        bids_count = Bid.objects.filter(
            auction_id=auction.id, is_sealed=True
        ).count()

    if bids_count == 0:
        auction.status = Auction.Status.FAILED
        auction.save(update_fields=["status", "updated_at"])
        notify_auction_failed_no_bids(auction=auction)
        broadcast_auction_status(
            auction_id=auction.id,
            payload={
                "auction": {
                    "id": auction.id,
                    "status": auction.status,
                    "updated_at": auction.updated_at.isoformat(),
                }
            },
        )
        return

    if auction.mode == Auction.Mode.OPEN:
        # Winner is the highest bid.
        auction.winner_bid_id = auction.highest_bid_id

    auction.status = Auction.Status.FINISHED
    auction.save(update_fields=["winner_bid_id", "status", "updated_at"])

    if auction.mode == Auction.Mode.OPEN:
        winner_bid = None
        if auction.winner_bid_id:
            winner_bid = (
                Bid.objects.select_related("broker")
                .filter(id=auction.winner_bid_id)
                .first()
            )
        notify_open_auction_finished_for_owner(
            auction=auction, winner_bid=winner_bid
        )
        if winner_bid is not None:
            notify_auction_result_awaiting_owner(
                auction=auction, winner_bid=winner_bid
            )
    else:
        notify_closed_auction_finished_for_owner(
            auction=auction, bids_count=bids_count
        )

        from .services.assignments import auto_select_closed_winner

        auto_winner = auto_select_closed_winner(auction=auction)
        if auto_winner is not None:
            notify_auction_result_awaiting_owner(
                auction=auction, winner_bid=auto_winner
            )

    broadcast_auction_status(
        auction_id=auction.id,
        payload={
            "auction": {
                "id": auction.id,
                "status": auction.status,
                "updated_at": auction.updated_at.isoformat(),
            }
        },
    )


@shared_task(bind=True, ignore_result=True)
def finish_auction(self, auction_id: int) -> None:
    with transaction.atomic():
        auction = (
            Auction.objects.select_for_update()
            .only(
                "id",
                "mode",
                "status",
                "highest_bid_id",
                "winner_bid_id",
                "end_date",
                "real_property_id",
                "owner_id",
            )
            .filter(id=auction_id)
            .first()
        )
        if not auction or auction.status in (
            Auction.Status.FINISHED,
            Auction.Status.CANCELLED,
            Auction.Status.FAILED,
        ):
            return

        if auction.end_date is None or timezone.now() < auction.end_date:
            return

        _finalize_auction(auction)


@shared_task(bind=True, ignore_result=True)
def sweep_overdue_auctions(self) -> dict:
    """
    Fallback CRON: every ~5 min find ACTIVE auctions whose end_date has
    passed but the one-off `finish_auction` task didn't run (worker
    restart, lost ClockedSchedule, etc.) and finalize them.
    """
    now = timezone.now()
    overdue_ids = list(
        Auction.objects.filter(
            status=Auction.Status.ACTIVE,
            end_date__lt=now,
        ).values_list("id", flat=True)
    )

    finished = 0
    failed = 0
    skipped = 0

    for auction_id in overdue_ids:
        try:
            with transaction.atomic():
                auction = (
                    Auction.objects.select_for_update()
                    .only(
                        "id",
                        "mode",
                        "status",
                        "highest_bid_id",
                        "winner_bid_id",
                        "end_date",
                        "real_property_id",
                        "owner_id",
                    )
                    .filter(id=auction_id)
                    .first()
                )
                if (
                    not auction
                    or auction.status != Auction.Status.ACTIVE
                    or auction.end_date is None
                    or auction.end_date >= now
                ):
                    skipped += 1
                    continue

                _finalize_auction(auction)
                if auction.status == Auction.Status.FAILED:
                    failed += 1
                else:
                    finished += 1
        except Exception:
            logger.exception(
                "sweep_overdue_auctions: failed to finalize auction %s",
                auction_id,
            )

    return {
        "checked": len(overdue_ids),
        "finished": finished,
        "failed": failed,
        "skipped": skipped,
    }
