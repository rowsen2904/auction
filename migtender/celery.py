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
    # Daily check for deals stuck in PENDING_DOCUMENTS > N days -> FAILED
    "mark_failed_pending_deals_daily": {
        "task": "deals.tasks.mark_failed_pending_deals",
        "schedule": crontab(hour=4, minute=15),  # every day at 04:15
    },
    "notifications-document-deadline-reminders": {
        "task": "notifications.tasks.send_document_deadline_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "notifications-overdue-deals": {
        "task": "notifications.tasks.notify_overdue_deals_task",
        "schedule": crontab(hour=9, minute=10),
    },
    "notifications-developer-confirm-reminders": {
        "task": "notifications.tasks.send_developer_confirm_reminders",
        "schedule": crontab(hour=10, minute=0),
    },
    "notifications-admin-daily-deals-summary": {
        "task": "notifications.tasks.send_admin_daily_deals_summary",
        "schedule": crontab(hour=8, minute=0),
    },
    "notifications-admin-daily-payments-summary": {
        "task": "notifications.tasks.send_admin_daily_payments_summary",
        "schedule": crontab(hour=8, minute=5),
    },
    # Transit settlement deadlines
    "settlement-broker-payout-deadlines": {
        "task": "payments.tasks.check_broker_payout_deadlines",
        "schedule": crontab(hour=9, minute=30),
    },
    "settlement-developer-payment-deadlines": {
        "task": "payments.tasks.check_developer_payment_deadlines",
        "schedule": crontab(hour=9, minute=40),
    },
}
