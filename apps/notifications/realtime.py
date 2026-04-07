from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notifications_group_name(user_id: int) -> str:
    return f"notifications_user_{user_id}"


def _group_send(*, user_id: int, event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        notifications_group_name(user_id),
        {
            "type": event_type,
            "payload": payload,
        },
    )


def broadcast_notification_created(
    *, user_id: int, notification: dict, unread_count: int
) -> None:
    _group_send(
        user_id=user_id,
        event_type="notification_created",
        payload={
            "notification": notification,
            "unread_count": unread_count,
        },
    )


def broadcast_notification_read(
    *, user_id: int, notification_id: int, read_at: str | None, unread_count: int
) -> None:
    _group_send(
        user_id=user_id,
        event_type="notification_read",
        payload={
            "notification_id": notification_id,
            "read_at": read_at,
            "unread_count": unread_count,
        },
    )


def broadcast_notifications_read_all(
    *, user_id: int, notification_ids: list[int], read_at: str | None, unread_count: int
) -> None:
    _group_send(
        user_id=user_id,
        event_type="notifications_read_all",
        payload={
            "notification_ids": notification_ids,
            "read_at": read_at,
            "unread_count": unread_count,
        },
    )
