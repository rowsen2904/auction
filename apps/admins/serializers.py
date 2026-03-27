from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from properties.models import Property
from rest_framework import serializers

from apps.users.serializers import (
    BrokerInfoSerializer,
    DeveloperInfoSerializer,
    UserDocumentSerializer,
)

User = get_user_model()


class BrokerVerificationSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=("accept", "reject"))
    reason = serializers.CharField(
        required=False,
        allow_blank=False,
        trim_whitespace=True,
        max_length=1000,
    )

    def validate(self, attrs):
        action = attrs["action"]
        reason = (attrs.get("reason") or "").strip()

        if action == "reject":
            if not reason:
                raise serializers.ValidationError(
                    {"reason": _("Причина отказа обязательна.")}
                )
            attrs["reason"] = reason
        else:
            attrs["reason"] = None

        return attrs


class UserSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()
    developer = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "broker",
            "developer",
            "documents",
        ]

    def get_broker(self, obj):
        broker = getattr(obj, "broker", None)
        if not broker:
            return None
        return BrokerInfoSerializer(broker, context=self.context).data

    def get_developer(self, obj):
        developer = getattr(obj, "developer", None)
        if not developer:
            return None
        return DeveloperInfoSerializer(developer, context=self.context).data

    def get_documents(self, obj):
        if obj.role == User.Roles.ADMIN:
            return []
        return UserDocumentSerializer(
            obj.documents.all(),
            many=True,
            context=self.context,
        ).data


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
            "deadline",
            "status",
            "moderation_status",
            "moderation_rejection_reason",
            "created_at",
        ]
        read_only_fields = fields


class PropertyRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=1000,
    )

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Причина отказа обязательна."))
        return value
