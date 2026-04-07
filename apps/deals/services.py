from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .models import Deal, DealLog


def create_deal_from_bid(*, auction, bid, real_property) -> Deal:
    """
    OPEN:
      - real_property == auction.real_property
      - amount = bid.amount
      - lot_bid_amount = bid.amount

    CLOSED:
      - one deal per assigned property
      - amount = real_property.price
      - lot_bid_amount = bid.amount
    """
    if real_property is None:
        raise ValidationError(
            {"detail": "Для создания сделки нужен объект недвижимости."}
        )

    deadline_days = getattr(settings, "DEAL_DOCUMENT_DEADLINE_DAYS", 7)
    deadline = auction.end_date + timedelta(days=deadline_days)

    if auction.mode == auction.Mode.OPEN:
        deal_amount = bid.amount
    else:
        deal_amount = real_property.price

    deal = Deal.objects.create(
        auction=auction,
        bid=bid,
        broker_id=bid.broker_id,
        developer_id=auction.owner_id,
        real_property_id=real_property.id,
        amount=deal_amount,
        lot_bid_amount=bid.amount,
        status=Deal.Status.PENDING_DOCUMENTS,
        obligation_status=Deal.ObligationStatus.ACTIVE,
        document_deadline=deadline,
    )

    DealLog.objects.create(
        deal=deal,
        action=DealLog.Action.CREATED,
        actor=None,
        detail=(
            f"Сделка создана по аукциону #{auction.id}, "
            f"ставка #{bid.id}, объект #{real_property.id}."
        ),
    )

    from .tasks import send_deal_created_email

    send_deal_created_email.delay(deal.id)

    from notifications.services import notify_broker_auction_won

    notify_broker_auction_won(deal=deal)

    return deal


def create_payments_for_deal(deal: Deal) -> None:
    from payments.models import Payment

    prop = deal.real_property

    broker_rate = prop.commission_rate or Decimal("0.00")
    if broker_rate > 0:
        broker_amount = (deal.amount * broker_rate / 100).quantize(Decimal("0.01"))
        Payment.objects.get_or_create(
            deal=deal,
            type=Payment.Type.DEVELOPER_COMMISSION,
            defaults={
                "amount": broker_amount,
                "rate": broker_rate,
                "status": Payment.Status.PENDING,
            },
        )

    platform_rate = Decimal(
        str(getattr(settings, "PLATFORM_COMMISSION_RATE", Decimal("0.40")))
    )
    platform_amount = (deal.amount * platform_rate / 100).quantize(Decimal("0.01"))
    Payment.objects.get_or_create(
        deal=deal,
        type=Payment.Type.PLATFORM_COMMISSION,
        defaults={
            "amount": platform_amount,
            "rate": platform_rate,
            "status": Payment.Status.PENDING,
        },
    )

    from notifications.services import notify_payments_created

    notify_payments_created(deal=deal)


def submit_deal_for_review(deal: Deal, actor=None) -> bool:
    if deal.status != Deal.Status.PENDING_DOCUMENTS:
        raise ValidationError(
            {
                "detail": "Отправка на проверку возможна только в статусе ожидания документов."
            }
        )

    has_both_docs = bool(deal.ddu_document) and bool(deal.payment_proof_document)
    if not has_both_docs:
        raise ValidationError(
            {
                "detail": (
                    "Для отправки на проверку необходимо загрузить "
                    "и ДДУ, и подтверждение оплаты."
                )
            }
        )

    deal.status = Deal.Status.ADMIN_REVIEW
    deal.admin_rejection_reason = ""
    deal.developer_rejection_reason = ""
    deal.save(
        update_fields=[
            "status",
            "admin_rejection_reason",
            "developer_rejection_reason",
            "updated_at",
        ]
    )

    DealLog.objects.create(
        deal=deal,
        action=DealLog.Action.SUBMITTED_FOR_REVIEW,
        actor=actor,
        detail="Сделка отправлена на проверку администратору.",
    )

    from .tasks import send_deal_submitted_for_review_email

    send_deal_submitted_for_review_email.delay(deal.id)

    from notifications.services import notify_deal_submitted_for_review

    notify_deal_submitted_for_review(deal=deal)

    return True
