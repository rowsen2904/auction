from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import Deal, DealLog


def create_deal_from_bid(*, auction, bid) -> Deal:
    """Create a Deal from a finished auction's winning bid."""
    deadline_days = getattr(settings, "DEAL_DOCUMENT_DEADLINE_DAYS", 7)
    deadline = auction.end_date + timedelta(days=deadline_days)

    deal = Deal.objects.create(
        auction=auction,
        bid=bid,
        broker_id=bid.broker_id,
        developer_id=auction.owner_id,
        real_property_id=auction.real_property_id,
        amount=bid.amount,
        status=Deal.Status.PENDING_DOCUMENTS,
        obligation_status=Deal.ObligationStatus.ACTIVE,
        document_deadline=deadline,
    )

    DealLog.objects.create(
        deal=deal,
        action=DealLog.Action.CREATED,
        actor=None,
        detail=f"Сделка создана по аукциону #{auction.id}, ставка #{bid.id}.",
    )

    # Send email notification to broker (async)
    from .tasks import send_deal_created_email

    send_deal_created_email.delay(deal.id)

    return deal


def create_payments_for_deal(deal: Deal) -> None:
    """Create payment records when deal is confirmed."""
    from payments.models import Payment

    prop = deal.real_property

    # Developer commission (individual rate, auto-paid offline)
    commission_rate = prop.commission_rate or Decimal("0.00")
    if commission_rate > 0:
        dev_amount = (deal.amount * commission_rate / 100).quantize(Decimal("0.01"))
        Payment.objects.create(
            deal=deal,
            type=Payment.Type.DEVELOPER_COMMISSION,
            amount=dev_amount,
            rate=commission_rate,
            status=Payment.Status.PAID,
        )

    # Platform commission (fixed 0.8%, pending until admin uploads receipt)
    platform_rate = getattr(settings, "PLATFORM_COMMISSION_RATE", Decimal("0.80"))
    platform_amount = (deal.amount * platform_rate / 100).quantize(Decimal("0.01"))
    Payment.objects.create(
        deal=deal,
        type=Payment.Type.PLATFORM_COMMISSION,
        amount=platform_amount,
        rate=platform_rate,
        status=Payment.Status.PENDING,
    )


def check_and_transition_to_review(deal: Deal, actor=None) -> bool:
    """Transition to admin_review when BOTH docs uploaded OR comment filled."""
    if deal.status != Deal.Status.PENDING_DOCUMENTS:
        return False

    has_both_docs = bool(deal.ddu_document) and bool(deal.payment_proof_document)
    has_comment = bool(deal.broker_comment.strip())

    if has_both_docs or has_comment:
        deal.status = Deal.Status.ADMIN_REVIEW
        deal.save(update_fields=["status", "updated_at"])

        DealLog.objects.create(
            deal=deal,
            action=DealLog.Action.SUBMITTED_FOR_REVIEW,
            actor=actor,
            detail="Автоматический переход на проверку администратором.",
        )

        from .tasks import send_deal_submitted_for_review_email

        send_deal_submitted_for_review_email.delay(deal.id)
        return True

    return False
