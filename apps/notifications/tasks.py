from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .services import (
    notify_admin_daily_deals_summary,
    notify_admin_daily_payments_summary,
    notify_broker_deadline_reminder,
    notify_developer_confirm_reminder,
    notify_overdue_deal,
)


@shared_task(bind=True, ignore_result=True)
def send_document_deadline_reminders(self) -> dict:
    from deals.models import Deal

    now = timezone.now()
    today = now.date()
    target_dates = {
        3: today + timedelta(days=3),
        1: today + timedelta(days=1),
    }

    reminded = {3: 0, 1: 0}

    qs = Deal.objects.select_related("broker", "real_property", "auction").filter(
        status=Deal.Status.PENDING_DOCUMENTS,
        obligation_status=Deal.ObligationStatus.ACTIVE,
    )

    for deal in qs:
        deadline_date = timezone.localtime(deal.document_deadline).date()
        for days_left, target_date in target_dates.items():
            if deadline_date == target_date:
                notify_broker_deadline_reminder(deal=deal, days_left=days_left)
                reminded[days_left] += 1

    return {"reminded_3d": reminded[3], "reminded_1d": reminded[1]}


@shared_task(bind=True, ignore_result=True)
def notify_overdue_deals_task(self) -> dict:
    from deals.models import Deal

    overdue_qs = Deal.objects.select_related("broker", "real_property").filter(
        obligation_status=Deal.ObligationStatus.OVERDUE,
    )

    count = 0
    for deal in overdue_qs:
        notify_overdue_deal(deal=deal)
        count += 1

    return {"overdue_notified": count}


@shared_task(bind=True, ignore_result=True)
def send_developer_confirm_reminders(self) -> dict:
    from deals.models import Deal

    threshold_days = int(
        getattr(settings, "NOTIFICATION_DEVELOPER_CONFIRM_REMINDER_DAYS", 3)
    )
    threshold_dt = timezone.now() - timedelta(days=threshold_days)

    qs = Deal.objects.select_related("developer", "real_property").filter(
        status=Deal.Status.DEVELOPER_CONFIRM,
        updated_at__lte=threshold_dt,
    )

    count = 0
    for deal in qs:
        waiting_days = max((timezone.now() - deal.updated_at).days, threshold_days)
        notify_developer_confirm_reminder(deal=deal, waiting_days=waiting_days)
        count += 1

    return {"developer_confirm_reminders": count}


@shared_task(bind=True, ignore_result=True)
def send_admin_daily_deals_summary(self) -> dict:
    from deals.models import Deal
    from django.contrib.auth import get_user_model

    User = get_user_model()
    count = Deal.objects.filter(status=Deal.Status.ADMIN_REVIEW).count()
    today = timezone.localdate()

    admins = User.objects.filter(role=User.Roles.ADMIN, is_active=True)
    admin_count = 0
    for admin in admins:
        notify_admin_daily_deals_summary(
            admin_user=admin, count=count, summary_date=today
        )
        admin_count += 1

    return {"admins": admin_count, "deals_waiting_review": count}


@shared_task(bind=True, ignore_result=True)
def send_admin_daily_payments_summary(self) -> dict:
    from django.contrib.auth import get_user_model
    from payments.models import Payment

    User = get_user_model()
    qs = Payment.objects.filter(status=Payment.Status.PENDING)
    count = qs.count()
    total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    today = timezone.localdate()

    admins = User.objects.filter(role=User.Roles.ADMIN, is_active=True)
    admin_count = 0
    for admin in admins:
        notify_admin_daily_payments_summary(
            admin_user=admin,
            count=count,
            total=total,
            summary_date=today,
        )
        admin_count += 1

    return {"admins": admin_count, "payments_waiting": count, "total": str(total)}
