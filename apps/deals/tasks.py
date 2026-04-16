from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def send_deal_created_email(self, deal_id: int) -> None:
    from .models import Deal

    try:
        deal = Deal.objects.select_related("broker", "real_property").get(id=deal_id)
    except Deal.DoesNotExist:
        return

    deadline_str = deal.document_deadline.strftime("%d.%m.%Y")
    send_mail(
        subject=f"MIG Tender — Новая сделка #{deal.id}",
        message=(
            f"Сделка #{deal.id} создана по аукциону #{deal.auction_id}.\n"
            f"Объект: {deal.real_property.address}\n\n"
            f"Загрузите документы (ДДУ и подтверждение оплаты) до {deadline_str}.\n"
            f"Или оставьте комментарий, если документы переданы вне платформы."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[deal.broker.email],
        fail_silently=True,
    )


@shared_task(bind=True, ignore_result=True)
def send_deal_submitted_for_review_email(self, deal_id: int) -> None:
    from users.models import User

    from .models import Deal

    try:
        deal = Deal.objects.select_related("real_property").get(id=deal_id)
    except Deal.DoesNotExist:
        return

    admin_emails = list(
        User.objects.filter(role=User.Roles.ADMIN, is_active=True).values_list(
            "email", flat=True
        )
    )
    if not admin_emails:
        return

    send_mail(
        subject=f"MIG Tender — Сделка #{deal.id} ожидает проверки",
        message=(
            f"Сделка #{deal.id} по объекту «{deal.real_property.address}» "
            f"передана на проверку.\n"
            f"Перейдите в панель администратора для проверки документов."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=admin_emails,
        fail_silently=True,
    )


@shared_task(bind=True, ignore_result=True)
def send_deal_status_email(
    self, deal_id: int, recipient_email: str, subject: str, message: str
) -> None:
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        fail_silently=True,
    )


@shared_task(bind=True, ignore_result=True)
def check_overdue_deals(self) -> dict:
    """Daily task: mark overdue deals where document deadline has passed."""
    from .models import Deal, DealLog

    now = timezone.now()

    overdue_deals = Deal.objects.filter(
        status=Deal.Status.PENDING_DOCUMENTS,
        obligation_status=Deal.ObligationStatus.ACTIVE,
        document_deadline__lt=now,
    )

    deal_ids = list(overdue_deals.values_list("id", flat=True))
    updated = overdue_deals.update(obligation_status=Deal.ObligationStatus.OVERDUE)

    # Create log entries
    already_logged = set(
        DealLog.objects.filter(
            deal_id__in=deal_ids,
            action=DealLog.Action.MARKED_OVERDUE,
        ).values_list("deal_id", flat=True)
    )

    logs_to_create = [
        DealLog(
            deal_id=deal_id,
            action=DealLog.Action.MARKED_OVERDUE,
            detail="Дедлайн загрузки документов истёк. Обязательство просрочено.",
        )
        for deal_id in deal_ids
        if deal_id not in already_logged
    ]
    if logs_to_create:
        DealLog.objects.bulk_create(logs_to_create)

    logger.info("check_overdue_deals: marked %d deals as overdue", updated)
    return {"marked_overdue": updated}


@shared_task(bind=True, ignore_result=True)
def mark_failed_pending_deals(self) -> dict:
    """Daily task: mark deals stuck in PENDING_DOCUMENTS longer than
    DEAL_PENDING_DOCUMENTS_FAIL_DAYS as FAILED. This is terminal — the deal
    cannot be reopened; the developer must relist the property in a new auction."""
    from notifications.services import notify_deal_failed

    from .models import Deal, DealLog

    threshold_days = int(getattr(settings, "DEAL_PENDING_DOCUMENTS_FAIL_DAYS", 5))
    threshold_dt = timezone.now() - timedelta(days=threshold_days)

    stale_qs = Deal.objects.select_related(
        "broker", "developer", "real_property", "auction"
    ).filter(
        status=Deal.Status.PENDING_DOCUMENTS,
        created_at__lt=threshold_dt,
    )

    failed_ids: list[int] = []
    for deal in stale_qs:
        with transaction.atomic():
            locked = (
                Deal.objects.select_for_update()
                .filter(id=deal.id, status=Deal.Status.PENDING_DOCUMENTS)
                .first()
            )
            if locked is None:
                continue

            locked.status = Deal.Status.FAILED
            locked.obligation_status = Deal.ObligationStatus.OVERDUE
            locked.save(update_fields=["status", "obligation_status", "updated_at"])

            DealLog.objects.create(
                deal=locked,
                action=DealLog.Action.MARKED_FAILED,
                detail=(
                    f"Сделка автоматически помечена как несостоявшаяся: "
                    f"документы не загружены за {threshold_days} дней."
                ),
            )
            failed_ids.append(locked.id)

            days_in_pending = max(
                (timezone.now() - locked.created_at).days, threshold_days
            )
            transaction.on_commit(
                lambda d=deal, dp=days_in_pending: notify_deal_failed(
                    deal=d, days_in_pending=dp
                )
            )

    logger.info(
        "mark_failed_pending_deals: marked %d deals as FAILED (threshold=%d days)",
        len(failed_ids),
        threshold_days,
    )
    return {"marked_failed": len(failed_ids), "threshold_days": threshold_days}
