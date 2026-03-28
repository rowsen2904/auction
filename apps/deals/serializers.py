from rest_framework import serializers

from .models import Deal, DealLog


class DealLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = DealLog
        fields = ["id", "action", "actor_id", "actor_email", "detail", "created_at"]


class DealListSerializer(serializers.ModelSerializer):
    broker_name = serializers.SerializerMethodField()
    developer_name = serializers.SerializerMethodField()
    property_address = serializers.CharField(
        source="real_property.address", read_only=True
    )
    auction_mode = serializers.CharField(source="auction.mode", read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "auction_id",
            "real_property_id",
            "broker_id",
            "developer_id",
            "broker_name",
            "developer_name",
            "property_address",
            "auction_mode",
            "amount",
            "status",
            "obligation_status",
            "document_deadline",
            "created_at",
            "updated_at",
        ]

    def get_broker_name(self, obj):
        broker = obj.broker
        return f"{broker.first_name} {broker.last_name}".strip() or broker.email

    def get_developer_name(self, obj):
        dev = getattr(obj.developer, "developer", None)
        if dev and dev.company_name:
            return dev.company_name
        return f"{obj.developer.first_name} {obj.developer.last_name}".strip() or obj.developer.email


class DealDetailSerializer(DealListSerializer):
    ddu_document = serializers.SerializerMethodField()
    payment_proof_document = serializers.SerializerMethodField()
    logs = DealLogSerializer(many=True, read_only=True)
    commission_rate = serializers.DecimalField(
        source="real_property.commission_rate",
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )
    property_price = serializers.DecimalField(
        source="real_property.price",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta(DealListSerializer.Meta):
        fields = DealListSerializer.Meta.fields + [
            "ddu_document",
            "payment_proof_document",
            "broker_comment",
            "admin_rejection_reason",
            "developer_rejection_reason",
            "commission_rate",
            "property_price",
            "logs",
        ]

    def _build_url(self, file_field):
        if not file_field:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(file_field.url) if request else file_field.url

    def get_ddu_document(self, obj):
        return self._build_url(obj.ddu_document)

    def get_payment_proof_document(self, obj):
        return self._build_url(obj.payment_proof_document)


class DDUUploadSerializer(serializers.Serializer):
    ddu_document = serializers.FileField()


class PaymentProofUploadSerializer(serializers.Serializer):
    payment_proof_document = serializers.FileField()


class BrokerCommentSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000, allow_blank=False)


class RejectReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=2000)
