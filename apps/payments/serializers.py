from rest_framework import serializers

from .models import DealSettlement, Payment


class PaymentListSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(
        source="deal.real_property.address", read_only=True
    )
    auction_id = serializers.IntegerField(source="deal.auction_id", read_only=True)
    broker_id = serializers.IntegerField(source="deal.broker_id", read_only=True)
    developer_id = serializers.IntegerField(source="deal.developer_id", read_only=True)
    receipt_document = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "deal_id",
            "property_name",
            "auction_id",
            "broker_id",
            "developer_id",
            "type",
            "amount",
            "rate",
            "status",
            "receipt_document",
            "created_at",
            "updated_at",
        ]

    def get_receipt_document(self, obj):
        if not obj.receipt_document:
            return None
        request = self.context.get("request")
        return (
            request.build_absolute_uri(obj.receipt_document.url)
            if request
            else obj.receipt_document.url
        )


class PaymentSummarySerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    from_developers = serializers.DecimalField(max_digits=14, decimal_places=2)
    from_platform = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)


class DeveloperPaymentSummarySerializer(serializers.Serializer):
    total_to_pay = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending = serializers.DecimalField(max_digits=14, decimal_places=2)


class ReceiptUploadSerializer(serializers.Serializer):
    receipt_document = serializers.FileField()


# --- Transit settlement ---


class DealSettlementSerializer(serializers.ModelSerializer):
    deal_id = serializers.IntegerField(read_only=True)
    property_name = serializers.CharField(
        source="deal.real_property.address", read_only=True
    )
    auction_id = serializers.IntegerField(source="deal.auction_id", read_only=True)
    broker_id = serializers.IntegerField(source="deal.broker_id", read_only=True)
    broker_name = serializers.SerializerMethodField()
    developer_id = serializers.IntegerField(source="deal.developer_id", read_only=True)
    developer_name = serializers.SerializerMethodField()
    deal_amount = serializers.DecimalField(
        source="deal.amount", max_digits=14, decimal_places=2, read_only=True
    )
    deal_status = serializers.CharField(source="deal.status", read_only=True)

    broker_payout_receipt = serializers.SerializerMethodField()
    developer_receipt = serializers.SerializerMethodField()
    is_financially_closed = serializers.BooleanField(read_only=True)
    broker_payout_overdue = serializers.BooleanField(read_only=True)
    developer_payment_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = DealSettlement
        fields = [
            "id",
            "deal_id",
            "property_name",
            "auction_id",
            "broker_id",
            "broker_name",
            "developer_id",
            "developer_name",
            "deal_amount",
            "deal_status",
            "broker_amount",
            "broker_rate",
            "platform_amount",
            "platform_rate",
            "total_from_developer",
            "paid_to_broker",
            "paid_to_broker_at",
            "broker_payout_receipt",
            "broker_payout_deadline",
            "broker_payout_overdue",
            "received_from_developer",
            "received_from_developer_at",
            "developer_receipt",
            "developer_receipt_uploaded_at",
            "developer_payment_deadline",
            "developer_payment_overdue",
            "is_financially_closed",
            "created_at",
            "updated_at",
        ]

    def get_broker_name(self, obj):
        u = obj.deal.broker
        full = f"{u.first_name or ''} {u.last_name or ''}".strip()
        return full or u.email

    def get_developer_name(self, obj):
        u = obj.deal.developer
        full = f"{u.first_name or ''} {u.last_name or ''}".strip()
        dev = getattr(u, "developer", None)
        if dev and dev.company_name:
            return dev.company_name
        return full or u.email

    def _abs(self, f):
        if not f:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(f.url) if req else f.url

    def get_broker_payout_receipt(self, obj):
        return self._abs(obj.broker_payout_receipt)

    def get_developer_receipt(self, obj):
        return self._abs(obj.developer_receipt)


class SettlementSummarySerializer(serializers.Serializer):
    total_settlements = serializers.IntegerField()
    closed = serializers.IntegerField()
    awaiting_broker_payout = serializers.IntegerField()
    awaiting_developer_payment = serializers.IntegerField()
    total_owed_by_developers = serializers.DecimalField(
        max_digits=18, decimal_places=2
    )
    total_paid_to_brokers = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_received_from_developers = serializers.DecimalField(
        max_digits=18, decimal_places=2
    )


class MarkPaidToBrokerSerializer(serializers.Serializer):
    broker_payout_receipt = serializers.FileField()


class ConfirmDeveloperReceiptSerializer(serializers.Serializer):
    """No payload — admin just confirms."""

    pass


class UploadDeveloperReceiptSerializer(serializers.Serializer):
    developer_receipt = serializers.FileField()
