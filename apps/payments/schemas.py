from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import serializers

from .serializers import (
    DeveloperPaymentSummarySerializer,
    PaymentListSerializer,
    PaymentSummarySerializer,
    ReceiptUploadSerializer,
)


class DRFDetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class ReceiptUploadSuccessSerializer(serializers.Serializer):
    detail = serializers.CharField()


PAYMENT_LIST_DOC = """
List payments visible to current user.

Access rules:
- admin: sees all payments
- developer: sees only own developer commission payments
- broker: sees payments linked to own broker deals
"""

PAYMENT_SUMMARY_DOC = """
Get aggregated payment summary for current user.

Response depends on role:
- developer:
    - total_to_pay
    - paid
    - pending
- broker / admin:
    - total
    - from_developers
    - from_platform
    - pending
    - paid
"""

UPLOAD_RECEIPT_DOC = """
Upload receipt for a payment and mark it as paid.

Rules:
- admin only
- request content type: multipart/form-data
- only PLATFORM_COMMISSION payment can receive a receipt
- if payment is already PAID, upload is rejected
"""


payment_list_schema = extend_schema(
    summary="List payments",
    description=PAYMENT_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=PaymentListSerializer(many=True),
            description="List of payments visible to current user.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
    },
    tags=["Payments"],
)

payment_summary_schema = extend_schema(
    summary="Get payment summary",
    description=PAYMENT_SUMMARY_DOC,
    responses={
        200: OpenApiResponse(
            response=PolymorphicProxySerializer(
                component_name="PaymentSummaryResponse",
                serializers=[
                    PaymentSummarySerializer,
                    DeveloperPaymentSummarySerializer,
                ],
                resource_type_field_name=None,
            ),
            description="Summary payload depends on current user role.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
    },
    tags=["Payments"],
)

payment_upload_receipt_schema = extend_schema(
    summary="Upload receipt and mark payment as paid",
    description=UPLOAD_RECEIPT_DOC,
    request=ReceiptUploadSerializer,
    responses={
        200: OpenApiResponse(
            response=ReceiptUploadSuccessSerializer,
            description="Receipt uploaded, payment marked as paid.",
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Validation error.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (admin only).",
        ),
        404: OpenApiResponse(description="Payment not found."),
    },
    tags=["Payments"],
)
