from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Notification
from .realtime import (
    broadcast_notification_created,
    broadcast_notification_read,
    broadcast_notifications_read_all,
)
from .serializers import NotificationSerializer

User = get_user_model()


class NotificationEvent:
    NEW_BROKER_REGISTERED = "new_broker_registered"
    NEW_PROPERTY_PENDING = "new_property_pending"

    AUCTION_WON = "auction_won"
    AUCTION_NOT_SELECTED = "auction_not_selected"
    AUCTION_FINISHED_OPEN = "auction_finished_open"
    AUCTION_FINISHED_CLOSED = "auction_finished_closed"
    AUCTION_RESULT_CONFIRMED = "auction_result_confirmed"
    AUCTION_RESULT_REJECTED = "auction_result_rejected"
    AUCTION_WINNER_DECLINED = "auction_winner_declined"
    AUCTION_WINNER_PROMOTED = "auction_winner_promoted"
    DOCUMENTS_REQUESTED = "documents_requested"
    DOCUMENTS_REQUEST_ANSWERED = "documents_request_answered"

    DOCUMENTS_DEADLINE_3D = "documents_deadline_3d"
    DOCUMENTS_DEADLINE_1D = "documents_deadline_1d"
    OBLIGATION_OVERDUE = "obligation_overdue"
    DEAL_FAILED = "deal_failed"

    DEAL_SUBMITTED_FOR_REVIEW = "deal_submitted_for_review"
    ADMIN_APPROVED = "admin_approved"
    ADMIN_REJECTED = "admin_rejected"
    DEVELOPER_NEEDS_CONFIRM = "developer_needs_confirm"
    DEVELOPER_CONFIRM_REMINDER = "developer_confirm_reminder"
    DEVELOPER_CONFIRMED = "developer_confirmed"
    DEVELOPER_REJECTED = "developer_rejected"

    PAYOUT_CREATED = "payout_created"
    PAYOUT_PAID = "payout_paid"

    DAILY_DEALS_SUMMARY = "daily_deals_summary"
    DAILY_PAYMENTS_SUMMARY = "daily_payments_summary"


def _display_user(user) -> str:
    if not user:
        return ""
    full_name = (
        f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    )
    return full_name or getattr(user, "email", f"#{getattr(user, 'id', 'unknown')}")


def _display_developer(user) -> str:
    developer = getattr(user, "developer", None)
    if developer and developer.company_name:
        return developer.company_name
    return _display_user(user)


def _admins_queryset():
    return User.objects.filter(role=User.Roles.ADMIN, is_active=True)


def _user_unread_count(user_id: int) -> int:
    return Notification.objects.filter(user_id=user_id, is_read=False).count()


def create_notification(
    *,
    user,
    category: str,
    event_type: str,
    message: str,
    title: str = "",
    data: dict | None = None,
    dedupe_key: str | None = None,
    auction=None,
    deal=None,
    payment=None,
    real_property=None,
) -> tuple[Notification, bool]:
    payload_data = data or {}

    defaults = {
        "user": user,
        "category": category,
        "event_type": event_type,
        "title": title,
        "message": message,
        "data": payload_data,
        "auction": auction,
        "deal": deal,
        "payment": payment,
        "real_property": real_property,
    }

    if dedupe_key:
        notification, created = Notification.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults=defaults,
        )
    else:
        notification = Notification.objects.create(**defaults)
        created = True

    if not created:
        return notification, False

    serialized = NotificationSerializer(notification).data

    def _after_commit() -> None:
        unread_count = _user_unread_count(notification.user_id)
        broadcast_notification_created(
            user_id=notification.user_id,
            notification=serialized,
            unread_count=unread_count,
        )

    transaction.on_commit(_after_commit)
    return notification, True


def create_notifications(*, users: Iterable, **kwargs) -> list[Notification]:
    created: list[Notification] = []
    for user in users:
        notification, was_created = create_notification(user=user, **kwargs)
        if was_created:
            created.append(notification)
    return created


def mark_notification_as_read(*, notification: Notification) -> bool:
    changed = notification.mark_as_read()
    if not changed:
        return False

    def _after_commit() -> None:
        unread_count = _user_unread_count(notification.user_id)
        broadcast_notification_read(
            user_id=notification.user_id,
            notification_id=notification.id,
            read_at=notification.read_at.isoformat() if notification.read_at else None,
            unread_count=unread_count,
        )

    transaction.on_commit(_after_commit)
    return True


def mark_all_notifications_as_read(*, user) -> list[int]:
    qs = Notification.objects.filter(user=user, is_read=False)
    notification_ids = list(qs.values_list("id", flat=True))
    if not notification_ids:
        return []

    read_at = timezone.now()
    qs.update(is_read=True, read_at=read_at)

    def _after_commit() -> None:
        unread_count = _user_unread_count(user.id)
        broadcast_notifications_read_all(
            user_id=user.id,
            notification_ids=notification_ids,
            read_at=read_at.isoformat(),
            unread_count=unread_count,
        )

    transaction.on_commit(_after_commit)
    return notification_ids


def notify_new_broker_registered(*, broker_user) -> None:
    message = (
        f"Новый брокер: {_display_user(broker_user)}. Документы ожидают верификации"
    )
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.USER,
            event_type=NotificationEvent.NEW_BROKER_REGISTERED,
            message=message,
            data={"broker_user_id": broker_user.id},
            dedupe_key=f"notif:new_broker:{broker_user.id}:admin:{admin.id}",
        )


def notify_new_property_pending(*, real_property) -> None:
    owner_name = _display_developer(real_property.owner)
    message = f"Новый объект на модерации: {real_property.address} от {owner_name}"
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.PROPERTY,
            event_type=NotificationEvent.NEW_PROPERTY_PENDING,
            message=message,
            data={"property_id": real_property.id, "owner_id": real_property.owner_id},
            real_property=real_property,
            dedupe_key=f"notif:new_property:{real_property.id}:admin:{admin.id}",
        )


def notify_broker_auction_won(*, deal) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    deadline = deal.document_deadline.strftime("%d.%m.%Y %H:%M")
    message = (
        f"Вы победили в аукционе #{deal.auction_id} по объекту {address}. "
        f"Загрузите документы до {deadline}"
    )
    create_notification(
        user=deal.broker,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_WON,
        message=message,
        auction=deal.auction,
        deal=deal,
        real_property=deal.real_property,
        data={
            "auction_id": deal.auction_id,
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
        },
        dedupe_key=f"notif:auction_won:deal:{deal.id}",
    )


def notify_closed_not_selected(*, auction, selected_broker_ids: list[int]) -> None:
    from auctions.models import Bid

    selected_broker_ids = set(selected_broker_ids)
    loser_ids = list(
        Bid.objects.filter(auction_id=auction.id, is_sealed=True)
        .exclude(broker_id__in=selected_broker_ids)
        .values_list("broker_id", flat=True)
        .distinct()
    )

    for broker_id in loser_ids:
        create_notification(
            user=User.objects.get(id=broker_id),
            category=Notification.Category.AUCTION,
            event_type=NotificationEvent.AUCTION_NOT_SELECTED,
            message=f"Вы не были выбраны в аукционе #{auction.id}",
            auction=auction,
            data={"auction_id": auction.id},
            dedupe_key=f"notif:auction_not_selected:{auction.id}:broker:{broker_id}",
        )


def notify_open_auction_finished_for_owner(*, auction, winner_bid=None) -> None:
    if winner_bid is None:
        winner_bid = getattr(auction, "winner_bid", None)

    if winner_bid:
        broker_name = _display_user(winner_bid.broker)
        amount = winner_bid.amount
        message = f"Аукцион #{auction.id} завершён. Победитель: {broker_name}, ставка {amount}"
    else:
        message = f"Аукцион #{auction.id} завершён. Победитель не определён"

    create_notification(
        user=auction.owner,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_FINISHED_OPEN,
        message=message,
        auction=auction,
        data={
            "auction_id": auction.id,
            "winner_bid_id": getattr(winner_bid, "id", None),
        },
        dedupe_key=f"notif:auction_finished_open:{auction.id}",
    )


def notify_closed_auction_finished_for_owner(*, auction, bids_count: int) -> None:
    create_notification(
        user=auction.owner,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_FINISHED_CLOSED,
        message=f"Аукцион #{auction.id} завершён. Выберите брокера из {bids_count} ставок",
        auction=auction,
        data={"auction_id": auction.id, "bids_count": bids_count},
        dedupe_key=f"notif:auction_finished_closed:{auction.id}",
    )


def notify_deal_submitted_for_review(*, deal) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    broker_name = _display_user(deal.broker)

    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.DEAL,
            event_type=NotificationEvent.DEAL_SUBMITTED_FOR_REVIEW,
            message=f"Сделка на проверке: {address}. Брокер: {broker_name}. Документы загружены",
            deal=deal,
            real_property=deal.real_property,
            data={
                "deal_id": deal.id,
                "property_id": deal.real_property_id,
                "broker_id": deal.broker_id,
            },
            dedupe_key=f"notif:deal_admin_review:{deal.id}:admin:{admin.id}",
        )

    create_notification(
        user=deal.developer,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEAL_SUBMITTED_FOR_REVIEW,
        message=(
            f"Брокер {broker_name} загрузил документы по {address}. Документы на проверке у админа"
        ),
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "broker_id": deal.broker_id,
        },
        dedupe_key=f"notif:deal_submitted_for_review:developer:{deal.id}",
    )


def notify_admin_approved(*, deal) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")

    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.ADMIN_APPROVED,
        message=f"Админ одобрил документы по {address}. Ожидаем подтверждения девелопера",
        deal=deal,
        real_property=deal.real_property,
        data={"deal_id": deal.id, "property_id": deal.real_property_id},
        dedupe_key=f"notif:admin_approved:broker:{deal.id}",
    )
    create_notification(
        user=deal.developer,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEVELOPER_NEEDS_CONFIRM,
        message=f"Админ проверил документы по {address}. Подтвердите сделку",
        deal=deal,
        real_property=deal.real_property,
        data={"deal_id": deal.id, "property_id": deal.real_property_id},
        dedupe_key=f"notif:developer_needs_confirm:{deal.id}",
    )


def notify_admin_rejected(*, deal, reason: str) -> None:
    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.ADMIN_REJECTED,
        message=f"Документы отклонены. Причина: {reason}. Загрузите повторно",
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "reason": reason,
        },
    )


def notify_developer_confirmed(*, deal) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEVELOPER_CONFIRMED,
        message=f"Девелопер подтвердил сделку по {address}. Сделка закрыта",
        deal=deal,
        real_property=deal.real_property,
        data={"deal_id": deal.id, "property_id": deal.real_property_id},
        dedupe_key=f"notif:developer_confirmed:broker:{deal.id}",
    )

    company_name = _display_developer(deal.developer)
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.DEAL,
            event_type=NotificationEvent.DEVELOPER_CONFIRMED,
            message=f"Девелопер {company_name} подтвердил сделку по {address}. Оформите выплату",
            deal=deal,
            real_property=deal.real_property,
            data={
                "deal_id": deal.id,
                "property_id": deal.real_property_id,
                "developer_id": deal.developer_id,
            },
            dedupe_key=f"notif:developer_confirmed:admin:{deal.id}:admin:{admin.id}",
        )


def notify_developer_rejected(*, deal, reason: str) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEVELOPER_REJECTED,
        message=f"Девелопер отклонил сделку по {address}. Причина: {reason}",
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "reason": reason,
        },
    )

    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.DEAL,
            event_type=NotificationEvent.DEVELOPER_REJECTED,
            message=f"Девелопер отклонил сделку по {address}. Причина: {reason}",
            deal=deal,
            real_property=deal.real_property,
            data={
                "deal_id": deal.id,
                "property_id": deal.real_property_id,
                "reason": reason,
            },
        )


def notify_payments_created(*, deal) -> None:
    payments = list(deal.payments.all())
    total = sum((payment.amount for payment in payments), Decimal("0.00"))
    dev_amount = sum(
        (
            payment.amount
            for payment in payments
            if payment.type == "developer_commission"
        ),
        Decimal("0.00"),
    )
    platform_amount = sum(
        (
            payment.amount
            for payment in payments
            if payment.type == "platform_commission"
        ),
        Decimal("0.00"),
    )
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    broker_rate = getattr(deal.real_property, "commission_rate", None) or Decimal(
        "0.00"
    )

    create_notification(
        user=deal.broker,
        category=Notification.Category.PAYMENT,
        event_type=NotificationEvent.PAYOUT_CREATED,
        message=f"Выплата подтверждена: {total} (дев. {dev_amount} + платф. {platform_amount})",
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "total": str(total),
            "from_developers": str(dev_amount),
            "from_platform": str(platform_amount),
        },
        dedupe_key=f"notif:payout_created:broker:{deal.id}",
    )
    create_notification(
        user=deal.developer,
        category=Notification.Category.PAYMENT,
        event_type=NotificationEvent.PAYOUT_CREATED,
        message=f"Сделка по {address} закрыта. Комиссия к выплате: {dev_amount} ({broker_rate}%)",
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "amount": str(dev_amount),
            "rate": str(broker_rate),
        },
        dedupe_key=f"notif:payout_created:developer:{deal.id}",
    )


def notify_payment_paid(*, payment) -> None:
    deal = payment.deal
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    broker_name = _display_user(deal.broker)

    create_notification(
        user=deal.broker,
        category=Notification.Category.PAYMENT,
        event_type=NotificationEvent.PAYOUT_PAID,
        message=f"Выплата выполнена: {payment.amount}. Чек доступен в «Мои выплаты»",
        payment=payment,
        deal=deal,
        real_property=deal.real_property,
        data={
            "payment_id": payment.id,
            "deal_id": deal.id,
            "amount": str(payment.amount),
        },
        dedupe_key=f"notif:payout_paid:broker:{payment.id}:{payment.status}",
    )
    create_notification(
        user=deal.developer,
        category=Notification.Category.PAYMENT,
        event_type=NotificationEvent.PAYOUT_PAID,
        message=f"Выплата {payment.amount} брокеру {broker_name} по {address} выполнена",
        payment=payment,
        deal=deal,
        real_property=deal.real_property,
        data={
            "payment_id": payment.id,
            "deal_id": deal.id,
            "amount": str(payment.amount),
            "broker_id": deal.broker_id,
        },
        dedupe_key=f"notif:payout_paid:developer:{payment.id}:{payment.status}",
    )


def notify_overdue_deal(*, deal) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    broker_name = _display_user(deal.broker)

    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.OBLIGATION_OVERDUE,
        message=f"Обязательство по {address} просрочено. Документы не загружены",
        deal=deal,
        real_property=deal.real_property,
        data={"deal_id": deal.id, "property_id": deal.real_property_id},
        dedupe_key=f"notif:deal_overdue:broker:{deal.id}",
    )
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.DEAL,
            event_type=NotificationEvent.OBLIGATION_OVERDUE,
            message=f"Обязательство брокера {broker_name} по {address} просрочено",
            deal=deal,
            real_property=deal.real_property,
            data={
                "deal_id": deal.id,
                "property_id": deal.real_property_id,
                "broker_id": deal.broker_id,
            },
            dedupe_key=f"notif:deal_overdue:admin:{deal.id}:admin:{admin.id}",
        )


def notify_auction_result_awaiting_owner(*, auction, winner_bid=None) -> None:
    if winner_bid is None:
        winner_bid = getattr(auction, "winner_bid", None)
    if winner_bid is None:
        return

    broker_name = _display_user(winner_bid.broker)
    message = (
        f"Аукцион #{auction.id} завершён. Победитель: {broker_name}, "
        f"ставка {winner_bid.amount}. Подтвердите или отклоните результат"
    )
    create_notification(
        user=auction.owner,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_FINISHED_OPEN,
        message=message,
        auction=auction,
        data={
            "auction_id": auction.id,
            "winner_bid_id": winner_bid.id,
            "awaiting_owner_decision": True,
        },
        dedupe_key=f"notif:auction_awaiting_owner:{auction.id}",
    )


def notify_auction_result_confirmed(*, auction, winner_bid) -> None:
    address_source = getattr(auction, "real_property", None)
    address = (
        getattr(address_source, "address", None)
        if address_source is not None
        else f"#{auction.id}"
    )
    broker_name = _display_user(winner_bid.broker)

    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.AUCTION,
            event_type=NotificationEvent.AUCTION_RESULT_CONFIRMED,
            message=(
                f"Девелопер подтвердил результат аукциона #{auction.id} "
                f"({address}). Победитель: {broker_name}"
            ),
            auction=auction,
            data={
                "auction_id": auction.id,
                "winner_bid_id": winner_bid.id,
                "broker_id": winner_bid.broker_id,
            },
            dedupe_key=f"notif:auction_result_confirmed:admin:{auction.id}:admin:{admin.id}",
        )


def notify_auction_result_rejected(*, auction, winner_bid, reason: str) -> None:
    owner_name = _display_developer(auction.owner)

    if winner_bid is not None:
        create_notification(
            user=winner_bid.broker,
            category=Notification.Category.AUCTION,
            event_type=NotificationEvent.AUCTION_RESULT_REJECTED,
            message=(
                f"Девелопер отклонил результат аукциона #{auction.id}. "
                f"Сделка по вашей ставке не будет создана. Причина: {reason}"
            ),
            auction=auction,
            data={
                "auction_id": auction.id,
                "winner_bid_id": winner_bid.id,
                "reason": reason,
            },
            dedupe_key=f"notif:auction_result_rejected:broker:{auction.id}",
        )

    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.AUCTION,
            event_type=NotificationEvent.AUCTION_RESULT_REJECTED,
            message=(
                f"Девелопер {owner_name} отклонил результат аукциона #{auction.id}. "
                f"Аукцион помечен как несостоявшийся. Причина: {reason}"
            ),
            auction=auction,
            data={
                "auction_id": auction.id,
                "reason": reason,
                "winner_bid_id": getattr(winner_bid, "id", None),
            },
            dedupe_key=f"notif:auction_result_rejected:admin:{auction.id}:admin:{admin.id}",
        )


def notify_auction_winner_declined(*, auction, declined_bid, reason: str) -> None:
    create_notification(
        user=declined_bid.broker,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_WINNER_DECLINED,
        message=(
            f"Девелопер отказался от вашей ставки по аукциону #{auction.id}. "
            f"Причина: {reason}"
        ),
        auction=auction,
        data={
            "auction_id": auction.id,
            "declined_bid_id": declined_bid.id,
            "reason": reason,
        },
        dedupe_key=f"notif:winner_declined:{auction.id}:bid:{declined_bid.id}",
    )


def notify_auction_winner_promoted(*, auction, new_winner_bid) -> None:
    broker_name = _display_user(new_winner_bid.broker)

    create_notification(
        user=new_winner_bid.broker,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.AUCTION_WINNER_PROMOTED,
        message=(
            f"Вы стали победителем аукциона #{auction.id} после отказа предыдущего "
            f"кандидата. Дождитесь подтверждения от девелопера"
        ),
        auction=auction,
        data={
            "auction_id": auction.id,
            "winner_bid_id": new_winner_bid.id,
        },
        dedupe_key=f"notif:winner_promoted:{auction.id}:bid:{new_winner_bid.id}",
    )
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.AUCTION,
            event_type=NotificationEvent.AUCTION_WINNER_PROMOTED,
            message=(
                f"В аукционе #{auction.id} новый победитель: {broker_name}. "
                f"Ожидается решение девелопера"
            ),
            auction=auction,
            data={
                "auction_id": auction.id,
                "winner_bid_id": new_winner_bid.id,
                "broker_id": new_winner_bid.broker_id,
            },
            dedupe_key=(
                f"notif:winner_promoted:admin:{auction.id}:"
                f"bid:{new_winner_bid.id}:admin:{admin.id}"
            ),
        )


def notify_broker_documents_requested(*, document_request) -> None:
    auction = document_request.auction
    description = document_request.description
    requester_name = _display_user(document_request.requested_by)

    create_notification(
        user=document_request.broker,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.DOCUMENTS_REQUESTED,
        message=(
            f"По аукциону #{auction.id} запрошены документы от {requester_name}. "
            f"{description[:120]}"
        ),
        auction=auction,
        data={
            "auction_id": auction.id,
            "document_request_id": document_request.id,
            "requested_by_id": document_request.requested_by_id,
        },
        dedupe_key=f"notif:documents_requested:{document_request.id}",
    )


def notify_documents_request_answered(*, document_request) -> None:
    auction = document_request.auction
    broker_name = _display_user(document_request.broker)
    file_count = document_request.response_documents.count()

    create_notification(
        user=document_request.requested_by,
        category=Notification.Category.AUCTION,
        event_type=NotificationEvent.DOCUMENTS_REQUEST_ANSWERED,
        message=(
            f"Брокер {broker_name} ответил на запрос по аукциону #{auction.id}: "
            f"загружено {file_count} файл(ов)"
        ),
        auction=auction,
        data={
            "auction_id": auction.id,
            "document_request_id": document_request.id,
            "broker_id": document_request.broker_id,
            "file_count": file_count,
        },
        dedupe_key=f"notif:documents_request_answered:{document_request.id}",
    )


def notify_deal_failed(*, deal, days_in_pending: int) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    broker_name = _display_user(deal.broker)

    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEAL_FAILED,
        message=(
            f"Сделка по {address} признана несостоявшейся: документы не были "
            f"загружены в течение {days_in_pending} дней"
        ),
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "days_in_pending": days_in_pending,
        },
        dedupe_key=f"notif:deal_failed:broker:{deal.id}",
    )
    create_notification(
        user=deal.developer,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEAL_FAILED,
        message=(
            f"Сделка по {address} признана несостоявшейся: брокер {broker_name} "
            f"не загрузил документы в течение {days_in_pending} дней. "
            f"Объект снова доступен для размещения"
        ),
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "broker_id": deal.broker_id,
            "days_in_pending": days_in_pending,
        },
        dedupe_key=f"notif:deal_failed:developer:{deal.id}",
    )
    for admin in _admins_queryset():
        create_notification(
            user=admin,
            category=Notification.Category.DEAL,
            event_type=NotificationEvent.DEAL_FAILED,
            message=(
                f"Сделка #{deal.id} по {address} автоматически помечена как "
                f"несостоявшаяся. Брокер {broker_name} не загрузил документы"
            ),
            deal=deal,
            real_property=deal.real_property,
            data={
                "deal_id": deal.id,
                "property_id": deal.real_property_id,
                "broker_id": deal.broker_id,
                "days_in_pending": days_in_pending,
            },
            dedupe_key=f"notif:deal_failed:admin:{deal.id}:admin:{admin.id}",
        )


def notify_broker_deadline_reminder(*, deal, days_left: int) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    if days_left == 3:
        message = f"До дедлайна загрузки документов по {address} осталось 3 дня"
        event_type = NotificationEvent.DOCUMENTS_DEADLINE_3D
    else:
        message = f"Завтра дедлайн загрузки документов по {address}"
        event_type = NotificationEvent.DOCUMENTS_DEADLINE_1D

    create_notification(
        user=deal.broker,
        category=Notification.Category.DEAL,
        event_type=event_type,
        message=message,
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "days_left": days_left,
        },
        dedupe_key=f"notif:deadline_reminder:{days_left}d:deal:{deal.id}",
    )


def notify_developer_confirm_reminder(*, deal, waiting_days: int) -> None:
    address = getattr(deal.real_property, "address", f"#{deal.real_property_id}")
    create_notification(
        user=deal.developer,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DEVELOPER_CONFIRM_REMINDER,
        message=f"Подтвердите сделку по {address}. Ждёт вашего ОК уже {waiting_days} дней",
        deal=deal,
        real_property=deal.real_property,
        data={
            "deal_id": deal.id,
            "property_id": deal.real_property_id,
            "waiting_days": waiting_days,
        },
        dedupe_key=f"notif:developer_confirm_reminder:deal:{deal.id}:days:{waiting_days}",
    )


def notify_admin_daily_deals_summary(*, admin_user, count: int, summary_date) -> None:
    create_notification(
        user=admin_user,
        category=Notification.Category.DEAL,
        event_type=NotificationEvent.DAILY_DEALS_SUMMARY,
        message=f"{count} сделок ожидают вашей проверки",
        data={"count": count, "date": str(summary_date)},
        dedupe_key=f"notif:daily_deals_summary:admin:{admin_user.id}:date:{summary_date}",
    )


def notify_admin_daily_payments_summary(
    *, admin_user, count: int, total: Decimal, summary_date
) -> None:
    create_notification(
        user=admin_user,
        category=Notification.Category.PAYMENT,
        event_type=NotificationEvent.DAILY_PAYMENTS_SUMMARY,
        message=f"{count} выплат ожидают подтверждения на сумму {total}",
        data={"count": count, "total": str(total), "date": str(summary_date)},
        dedupe_key=f"notif:daily_payments_summary:admin:{admin_user.id}:date:{summary_date}",
    )
