from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "migtender.settings")

app = Celery("migtender")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Daily cleanup of executed one-off tasks from django-celery-beat tables
    "cleanup_beat_tasks_daily": {
        "task": "migtender.tasks.cleanup_beat_tasks",
        "schedule": crontab(hour=3, minute=0),  # every day at 03:00
    },
    # Daily check for overdue deals
    "check_overdue_deals_daily": {
        "task": "deals.tasks.check_overdue_deals",
        "schedule": crontab(hour=4, minute=0),  # every day at 04:00
    },
}
