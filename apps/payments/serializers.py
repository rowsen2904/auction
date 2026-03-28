from rest_framework import serializers

from .models import Payment


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
