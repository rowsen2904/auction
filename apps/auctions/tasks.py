from __future__ import annotations

import json

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, PeriodicTask

from .models import Auction


def _activate_task_name(auction_id: int) -> str:
    # Stable deterministic name so we can update/replace safely
    return f"auction:{auction_id}:activate"


def _finish_task_name(auction_id: int) -> str:
    return f"auction:{auction_id}:finish"


def cancel_auction_status_tasks(*, auction_id: int) -> None:
    """
    Remove scheduled beat tasks for an auction (activate/finish).
    Safe to call multiple times.
    """
    PeriodicTask.objects.filter(
        name__in=[_activate_task_name(auction_id), _finish_task_name(auction_id)]
    ).delete()


def schedule_auction_status_tasks(*, auction_id: int, start_date, end_date) -> None:
    """
    Create/replace two one-off django-celery-beat tasks:
    - activate at start_date
    - finish at end_date
    """
    # Delete old tasks if they exist (important if you recreate/reschedule)
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
    """
    Switch DRAFT -> ACTIVE when start_date is reached.
    """
    with transaction.atomic():
        auction = Auction.objects.select_for_update().filter(id=auction_id).first()
        if not auction:
            return

        # Do nothing if auction is already finished/cancelled/active
        if auction.status != Auction.Status.DRAFT:
            return

        now = timezone.now()

        # Safety checks
        if now < auction.start_date:
            return
        if now >= auction.end_date:
            # If someone scheduled wrong or time jumped, finish instead
            auction.status = Auction.Status.FINISHED
            auction.save(update_fields=["status", "updated_at"])
            return

        auction.status = Auction.Status.ACTIVE
        auction.save(update_fields=["status", "updated_at"])


@shared_task(bind=True, ignore_result=True)
def finish_auction(self, auction_id: int) -> None:
    """
    Finish auction at end_date.
    For OPEN mode: auto-pick winner as highest_bid_id (if exists).
    """
    with transaction.atomic():
        auction = (
            Auction.objects.select_for_update()
            .only("id", "mode", "status", "highest_bid_id", "winner_bid_id", "end_date")
            .filter(id=auction_id)
            .first()
        )
        if not auction:
            return

        if auction.status in (
            Auction.Status.FINISHED,
            Auction.Status.CANCELLED,
        ):
            return

        # Optional safety: do not finish earlier than end_date
        if timezone.now() < auction.end_date:
            return

        if auction.mode == Auction.Mode.OPEN:
            auction.winner_bid_id = auction.highest_bid_id

        auction.status = Auction.Status.FINISHED
        auction.save(update_fields=["winner_bid_id", "status", "updated_at"])
