from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def check_broker_payout_deadlines(self) -> dict:
    """Daily: if a settlement wasn't paid to broker within 3 days — notify admins.

    Ежедневно бежит по не оплаченным брокеру расчётам, у которых дедлайн
    либо близок (< 24h), либо просрочен, и шлёт админам уведомление.
    """
    from notifications.models import Notification, NotificationEvent
    from notifications.services import create_notification

    from .models import DealSettlement

    User = get_user_model()
    now = timezone.now()
    warn_threshold = now + timedelta(hours=24)

    qs = DealSettlement.objects.filter(
        paid_to_broker=False,
        broker_payout_deadline__lte=warn_threshold,
    ).select_related("deal")

    admins = list(User.objects.filter(is_staff=True))
    sent = 0
    for s in qs:
        for admin in admins:
            is_overdue = s.broker_payout_deadline < now
            msg = (
                f"Просрочена выплата брокеру по сделке #{s.deal_id} "
                f"({s.broker_amount} ₽)"
                if is_overdue
                else f"Через сутки дедлайн выплаты брокеру по сделке #{s.deal_id}"
            )
            create_notification(
                user=admin,
                category=Notification.Category.PAYMENT,
                event_type=NotificationEvent.PAYMENT_PAID,
                message=msg,
                data={
                    "settlement_id": s.id,
                    "deal_id": s.deal_id,
                    "overdue": is_overdue,
                },
                dedupe_key=(
                    f"notif:broker_payout_{'overdue' if is_overdue else 'warn'}"
                    f":{s.id}:{admin.id}:{now.date()}"
                ),
            )
            sent += 1

    logger.info(
        "check_broker_payout_deadlines: notified for %d settlements (%d msgs)",
        qs.count(),
        sent,
    )
    return {"settlements": qs.count(), "notifications": sent}


@shared_task(bind=True, ignore_result=True)
def check_developer_payment_deadlines(self) -> dict:
    """Daily: remind developers about upcoming / overdue payment deadlines.

    Напоминаем за 30/7/1 день до дедлайна + при просрочке.
    """
    from notifications.models import Notification, NotificationEvent
    from notifications.services import create_notification

    from .models import DealSettlement

    now = timezone.now()
    qs = DealSettlement.objects.filter(received_from_developer=False).select_related(
        "deal", "deal__developer"
    )
    sent = 0
    for s in qs:
        days_left = (s.developer_payment_deadline - now).days
        overdue = now > s.developer_payment_deadline

        key = None
        if overdue:
            key = "overdue"
            msg = (
                f"Просрочена оплата по сделке #{s.deal_id} "
                f"({s.total_from_developer} ₽). Загрузите чек."
            )
        elif days_left <= 1:
            key = "1d"
            msg = (
                f"Завтра истекает срок оплаты {s.total_from_developer} ₽ "
                f"по сделке #{s.deal_id}."
            )
        elif days_left <= 7:
            key = "7d"
            msg = (
                f"Через неделю срок оплаты {s.total_from_developer} ₽ "
                f"по сделке #{s.deal_id}."
            )
        elif days_left <= 30:
            key = "30d"
            msg = (
                f"Через месяц срок оплаты {s.total_from_developer} ₽ "
                f"по сделке #{s.deal_id}."
            )
        else:
            continue

        create_notification(
            user=s.deal.developer,
            category=Notification.Category.PAYMENT,
            event_type=NotificationEvent.PAYMENT_PAID,
            message=msg,
            data={
                "settlement_id": s.id,
                "deal_id": s.deal_id,
                "overdue": overdue,
                "days_left": days_left,
            },
            dedupe_key=(
                f"notif:dev_payment_{key}:{s.id}:{now.date()}"
            ),
        )
        sent += 1

    logger.info(
        "check_developer_payment_deadlines: notified %d developers", sent
    )
    return {"notifications": sent}
