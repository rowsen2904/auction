from __future__ import annotations

import json

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, PeriodicTask

from .models import Auction, Bid
from .realtime import broadcast_auction_status


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


@shared_task(bind=True, ignore_result=True)
def finish_auction(self, auction_id: int) -> None:
    with transaction.atomic():
        auction = (
            Auction.objects.select_for_update()
            .select_related("real_property")
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
        ):
            return

        if timezone.now() < auction.end_date:
            return

        # OPEN: winner is highest bid automatically
        if auction.mode == Auction.Mode.OPEN:
            auction.winner_bid_id = auction.highest_bid_id

        auction.status = Auction.Status.FINISHED
        auction.save(update_fields=["winner_bid_id", "status", "updated_at"])

        # OPEN: auto-create deal if winner exists
        if auction.mode == Auction.Mode.OPEN and auction.winner_bid_id:
            from deals.services import create_deal_from_bid

            # real_property may be null for older auctions — fallback to M2M
            prop = auction.real_property
            if prop is None:
                prop = auction.properties.order_by("id").first()

            if prop is not None:
                bid = Bid.objects.get(id=auction.winner_bid_id)
                create_deal_from_bid(
                    auction=auction,
                    bid=bid,
                    real_property=prop,
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
