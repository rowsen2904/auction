from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, PeriodicTask


@shared_task(bind=True, ignore_result=True)
def cleanup_beat_tasks(self) -> dict:
    """
    Daily cleanup for django-celery-beat:
    - deletes executed one-off PeriodicTask rows (disabled + last_run_at set)
    - deletes orphan ClockedSchedule rows (no tasks reference them)
    """
    now = timezone.now()

    # Keep a small retention window for debugging (default: 2 hours)
    retention_hours = getattr(settings, "BEAT_CLEANUP_RETENTION_HOURS", 2)
    cutoff = now - timedelta(hours=retention_hours)

    deleted_tasks, _ = PeriodicTask.objects.filter(
        one_off=True,
        enabled=False,
        last_run_at__isnull=False,
        last_run_at__lt=cutoff,
    ).delete()

    deleted_clocked, _ = ClockedSchedule.objects.filter(
        clocked_time__lt=cutoff,
        periodictask__isnull=True,
    ).delete()

    return {
        "deleted_periodic_tasks": deleted_tasks,
        "deleted_clocked_schedules": deleted_clocked,
        "cutoff": cutoff.isoformat(),
    }
