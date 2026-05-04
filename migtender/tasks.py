"""
Project-wide Celery tasks (no app affiliation).

`cleanup_beat_tasks` is referenced from migtender/celery.py beat_schedule
("cleanup_beat_tasks_daily"). It removes stale executed records from
django-celery-beat and django-celery-results so those tables don't grow
unbounded.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def cleanup_beat_tasks(self) -> dict:
    """
    Idempotent housekeeping for django-celery-beat tables.

    - Disables and deletes one-off ClockedSchedule periodic tasks that have
      already fired and are older than 7 days.
    - Returns counts so it can be observed in Flower / logs.
    """
    deleted_periodic = 0
    deleted_clocked = 0
    deleted_solar = 0

    try:
        from django_celery_beat.models import (
            ClockedSchedule,
            PeriodicTask,
            SolarSchedule,
        )
    except Exception as exc:  # pragma: no cover — should never happen in prod
        logger.warning("django-celery-beat not available: %s", exc)
        return {
            "deleted_periodic": 0,
            "deleted_clocked": 0,
            "deleted_solar": 0,
        }

    cutoff = timezone.now() - timedelta(days=7)

    # One-off (clocked) tasks: older than cutoff and either disabled or already past clock_time
    stale_clocked_tasks = PeriodicTask.objects.filter(
        clocked__isnull=False,
        date_changed__lt=cutoff,
    )
    deleted_periodic = stale_clocked_tasks.count()
    stale_clocked_tasks.delete()

    # Orphaned ClockedSchedule rows (no PeriodicTask references them)
    orphan_clocked = ClockedSchedule.objects.exclude(
        id__in=PeriodicTask.objects.filter(clocked__isnull=False).values_list(
            "clocked_id", flat=True
        )
    )
    deleted_clocked = orphan_clocked.count()
    orphan_clocked.delete()

    # Orphaned SolarSchedule rows (rare, but cheap to clean)
    orphan_solar = SolarSchedule.objects.exclude(
        id__in=PeriodicTask.objects.filter(solar__isnull=False).values_list(
            "solar_id", flat=True
        )
    )
    deleted_solar = orphan_solar.count()
    orphan_solar.delete()

    result = {
        "deleted_periodic": deleted_periodic,
        "deleted_clocked": deleted_clocked,
        "deleted_solar": deleted_solar,
    }
    logger.info("cleanup_beat_tasks: %s", result)
    return result
