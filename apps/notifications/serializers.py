from __future__ import annotations

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "event_type",
            "title",
            "message",
            "data",
            "auction_id",
            "deal_id",
            "payment_id",
            "real_property_id",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationMarkReadSerializer(serializers.Serializer):
    notification_id = serializers.IntegerField(min_value=1)
