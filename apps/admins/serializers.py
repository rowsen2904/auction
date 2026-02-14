from django.contrib.auth import get_user_model
from properties.models import Property
from rest_framework import serializers

from apps.users.serializers import BrokerInfoSerializer, DeveloperInfoSerializer

User = get_user_model()


class BrokerVerificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=("accept", "reject"))


class UserSerializer(serializers.ModelSerializer):
    broker = BrokerInfoSerializer(read_only=True)
    developer = DeveloperInfoSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "broker",
            "developer",
        ]


class UserActiveUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class PendingPropertySerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)

    class Meta:
        model = Property
        fields = [
            "id",
            "owner_id",
            "type",
            "property_class",
            "address",
            "area",
            "price",
            "currency",
            "deadline",
            "status",
            "moderation_status",
            "created_at",
        ]
        read_only_fields = fields
