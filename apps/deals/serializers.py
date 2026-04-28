from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from helpers.file_tokens import (
    build_deal_document_url,
    build_developer_template_url,
)

from .models import Deal, DealLog


def _platform_rate() -> Decimal:
    return Decimal(str(getattr(settings, "PLATFORM_COMMISSION_RATE", Decimal("0.40"))))


class DealLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(
        source="actor.email", read_only=True, default=None
    )

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

    has_ddu = serializers.SerializerMethodField()
    has_payment_proof = serializers.SerializerMethodField()
    ddu_document = serializers.SerializerMethodField()
    payment_proof_document = serializers.SerializerMethodField()
    developer_ddu_template_url = serializers.SerializerMethodField()

    broker_commission_rate = serializers.DecimalField(
        source="real_property.commission_rate",
        max_digits=5,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    broker_commission_amount = serializers.SerializerMethodField()
    platform_commission_rate = serializers.SerializerMethodField()
    platform_commission_amount = serializers.SerializerMethodField()

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
            "lot_bid_amount",
            "status",
            "obligation_status",
            "document_deadline",
            "has_ddu",
            "has_payment_proof",
            "ddu_document",
            "payment_proof_document",
            "developer_ddu_template_url",
            "broker_commission_rate",
            "broker_commission_amount",
            "platform_commission_rate",
            "platform_commission_amount",
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
        return (
            f"{obj.developer.first_name} {obj.developer.last_name}".strip()
            or obj.developer.email
        )

    def get_has_ddu(self, obj):
        return bool(obj.ddu_document)

    def get_has_payment_proof(self, obj):
        return bool(obj.payment_proof_document)

    def get_ddu_document(self, obj):
        if not obj.ddu_document:
            return None
        return build_deal_document_url(
            self.context.get("request"), deal_id=obj.id, kind="ddu"
        )

    def get_payment_proof_document(self, obj):
        if not obj.payment_proof_document:
            return None
        return build_deal_document_url(
            self.context.get("request"), deal_id=obj.id, kind="payment_proof"
        )

    def get_developer_ddu_template_url(self, obj):
        dev = getattr(obj.developer, "developer", None)
        if not dev or not dev.ddu_template:
            return None
        return build_developer_template_url(
            self.context.get("request"), developer_user_id=obj.developer_id
        )

    def get_broker_commission_amount(self, obj):
        rate = obj.real_property.commission_rate or Decimal("0.00")
        return (obj.amount * rate / 100).quantize(Decimal("0.01"))

    def get_platform_commission_rate(self, obj):
        return _platform_rate()

    def get_platform_commission_amount(self, obj):
        rate = _platform_rate()
        return (obj.amount * rate / 100).quantize(Decimal("0.01"))


class DealDetailSerializer(DealListSerializer):
    ddu_document = serializers.SerializerMethodField()
    payment_proof_document = serializers.SerializerMethodField()
    logs = DealLogSerializer(many=True, read_only=True)

    # backward compatibility
    commission_rate = serializers.DecimalField(
        source="real_property.commission_rate",
        max_digits=5,
        decimal_places=2,
        read_only=True,
        allow_null=True,
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

    def get_ddu_document(self, obj):
        if not obj.ddu_document:
            return None
        return build_deal_document_url(
            self.context.get("request"), deal_id=obj.id, kind="ddu"
        )

    def get_payment_proof_document(self, obj):
        if not obj.payment_proof_document:
            return None
        return build_deal_document_url(
            self.context.get("request"), deal_id=obj.id, kind="payment_proof"
        )


class DDUUploadSerializer(serializers.Serializer):
    ddu_document = serializers.FileField()


class PaymentProofUploadSerializer(serializers.Serializer):
    payment_proof_document = serializers.FileField()


class BrokerCommentSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000, allow_blank=False)


class RejectReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=2000)
