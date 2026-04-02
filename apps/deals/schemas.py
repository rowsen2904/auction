from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import serializers

from .serializers import (
    BrokerCommentSerializer,
    DDUUploadSerializer,
    DealDetailSerializer,
    DealListSerializer,
    DealLogSerializer,
    PaymentProofUploadSerializer,
    RejectReasonSerializer,
)


class DRFDetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class DetailMessageSerializer(serializers.Serializer):
    detail = serializers.CharField()


DEAL_LIST_DOC = """
List deals visible to current user.

Access rules:
- admin: sees all deals
- developer: sees only own deals
- broker: sees only own deals

Filters:
- status
- obligation_status
- auction_id
- real_property_id
- broker_id
- developer_id

Pagination:
- page
- page_size

Returned list item includes:
- property_address
- auction_mode
- amount
- lot_bid_amount
- broker_commission_rate / broker_commission_amount
- platform_commission_rate / platform_commission_amount

Notes:
- OPEN auction usually creates one deal for one winning property.
- CLOSED lot auction may create multiple deals for one auction:
  one deal per assigned property.
"""

DEAL_DETAIL_DOC = """
Get deal details.

Access rules:
- admin: any deal
- developer: own deal only
- broker: own deal only

Includes:
- uploaded document URLs
- broker comment
- admin/developer rejection reasons
- property_price
- commission metrics
- logs
- lot_bid_amount
"""

UPLOAD_DDU_DOC = """
Upload DDU document for a deal.

Rules:
- authenticated broker of this deal only
- request content type: multipart/form-data
- available only while deal status is pending_documents
"""

UPLOAD_PAYMENT_PROOF_DOC = """
Upload payment proof document for a deal.

Rules:
- authenticated broker of this deal only
- request content type: multipart/form-data
- available only while deal status is pending_documents
"""

BROKER_COMMENT_DOC = """
Add broker comment for a deal.

Rules:
- authenticated broker of this deal only
- available only while deal status is pending_documents

Note:
- comment no longer auto-submits deal to review
"""

SUBMIT_FOR_REVIEW_DOC = """
Submit deal for admin review.

Rules:
- authenticated broker of this deal only
- available only while deal status is pending_documents
- both DDU and payment proof must already be uploaded

Effect:
- deal status changes to admin_review
- admin notification is sent
"""

ADMIN_APPROVE_DOC = """
Approve deal documents as admin.

Rules:
- admin only
- available only while deal status is admin_review

Effect:
- deal status changes to confirmed
- obligation status changes to fulfilled
- property status changes to sold
- payment records are created automatically
- broker and developer are notified
"""

ADMIN_REJECT_DOC = """
Reject deal documents as admin.

Rules:
- admin only
- available only while deal status is admin_review
- rejection reason is required

Effect:
- deal status changes back to pending_documents
- admin rejection reason is saved
- broker is notified
"""

DEAL_LOGS_DOC = """
List logs for a deal.

Access rules:
- admin
- broker of the deal
- developer of the deal
"""


deal_list_schema = extend_schema(
    summary="List deals",
    description=DEAL_LIST_DOC,
    parameters=[
        OpenApiParameter("status", str, required=False),
        OpenApiParameter("obligation_status", str, required=False),
        OpenApiParameter("auction_id", int, required=False),
        OpenApiParameter("real_property_id", int, required=False),
        OpenApiParameter("broker_id", int, required=False),
        OpenApiParameter("developer_id", int, required=False),
        OpenApiParameter("page", int, required=False),
        OpenApiParameter("page_size", int, required=False),
    ],
    responses={
        200: OpenApiResponse(
            response=DealListSerializer,
            description="Paginated list of deals visible to current user.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
    },
    tags=["Deals"],
)

deal_detail_schema = extend_schema(
    summary="Get deal detail",
    description=DEAL_DETAIL_DOC,
    responses={
        200: OpenApiResponse(
            response=DealDetailSerializer,
            description="Deal detail.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deals"],
)

deal_upload_ddu_schema = extend_schema(
    summary="Upload DDU document",
    description=UPLOAD_DDU_DOC,
    request=DDUUploadSerializer,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="DDU uploaded.",
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
            description="Forbidden.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Documents"],
)

deal_upload_payment_proof_schema = extend_schema(
    summary="Upload payment proof",
    description=UPLOAD_PAYMENT_PROOF_DOC,
    request=PaymentProofUploadSerializer,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Payment proof uploaded.",
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
            description="Forbidden.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Documents"],
)

deal_broker_comment_schema = extend_schema(
    summary="Add broker comment",
    description=BROKER_COMMENT_DOC,
    request=BrokerCommentSerializer,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Comment saved.",
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
            description="Forbidden.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Workflow"],
)

deal_submit_for_review_schema = extend_schema(
    summary="Submit deal for admin review",
    description=SUBMIT_FOR_REVIEW_DOC,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Deal submitted for review.",
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
            description="Forbidden.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Workflow"],
)

deal_admin_approve_schema = extend_schema(
    summary="Approve deal as admin",
    description=ADMIN_APPROVE_DOC,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Deal approved and payments created.",
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
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Workflow"],
)

deal_admin_reject_schema = extend_schema(
    summary="Reject deal as admin",
    description=ADMIN_REJECT_DOC,
    request=RejectReasonSerializer,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Deal rejected and broker notified.",
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
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Workflow"],
)

deal_logs_schema = extend_schema(
    summary="List deal logs",
    description=DEAL_LOGS_DOC,
    responses={
        200: OpenApiResponse(
            response=DealLogSerializer,
            description="List of deal logs.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden.",
        ),
        404: OpenApiResponse(description="Deal not found."),
    },
    tags=["Deal Logs"],
)
