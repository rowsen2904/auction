from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationMarkReadSerializer, NotificationSerializer
from .services import mark_all_notifications_as_read, mark_notification_as_read


class NotificationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by(
            "-created_at", "-id"
        )


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return Response({"unread_count": unread_count}, status=status.HTTP_200_OK)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = get_object_or_404(
            Notification,
            id=serializer.validated_data["notification_id"],
            user=request.user,
        )
        mark_notification_as_read(notification=notification)
        return Response({"detail": "OK"}, status=status.HTTP_200_OK)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        ids = mark_all_notifications_as_read(user=request.user)
        return Response({"notification_ids": ids}, status=status.HTTP_200_OK)
