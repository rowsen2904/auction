from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.shortcuts import get_object_or_404

from .models import Notification
from .realtime import notifications_group_name
from .serializers import NotificationSerializer
from .services import mark_all_notifications_as_read, mark_notification_as_read


@database_sync_to_async
def _snapshot_for_user(user_id: int, limit: int = 50) -> dict:
    qs = Notification.objects.filter(user_id=user_id).order_by("-created_at", "-id")[
        :limit
    ]
    notifications = NotificationSerializer(qs, many=True).data
    unread_count = Notification.objects.filter(user_id=user_id, is_read=False).count()
    return {
        "notifications": notifications,
        "unread_count": unread_count,
    }


@database_sync_to_async
def _mark_read_for_user(*, user_id: int, notification_id: int) -> dict:
    notification = get_object_or_404(Notification, id=notification_id, user_id=user_id)
    changed = mark_notification_as_read(notification=notification)
    return {
        "changed": changed,
        "notification_id": notification.id,
    }


@database_sync_to_async
def _mark_all_read_for_user(*, user) -> dict:
    ids = mark_all_notifications_as_read(user=user)
    return {"notification_ids": ids}


class UserNotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        self.user = user
        self.group_name = notifications_group_name(user.id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        snapshot = await _snapshot_for_user(user.id)
        await self.send_json(
            {
                "type": "notifications_snapshot",
                "notifications": snapshot["notifications"],
                "unread_count": snapshot["unread_count"],
            }
        )

    async def disconnect(self, code):
        user = getattr(self, "user", None)
        if user and hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")

        if message_type == "ping":
            await self.send_json({"type": "pong"})
            return

        if message_type == "mark_read":
            notification_id = content.get("notification_id") or content.get(
                "notificationId"
            )
            if not notification_id:
                await self.send_json(
                    {"type": "error", "detail": "notification_id обязателен."}
                )
                return
            await _mark_read_for_user(
                user_id=self.user.id, notification_id=int(notification_id)
            )
            return

        if message_type == "mark_all_read":
            await _mark_all_read_for_user(user=self.user)
            return

        await self.send_json({"type": "error", "detail": "Неизвестный тип сообщения."})

    async def notification_created(self, event):
        await self.send_json({"type": "notification_created", **event["payload"]})

    async def notification_read(self, event):
        await self.send_json({"type": "notification_read", **event["payload"]})

    async def notifications_read_all(self, event):
        await self.send_json({"type": "notifications_read_all", **event["payload"]})
