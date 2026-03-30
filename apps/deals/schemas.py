from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
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

Pagination:
- page
- page_size
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
- property commission rate and property price
- logs
"""

UPLOAD_DDU_DOC = """
Upload DDU document for a deal.

Rules:
- authenticated broker of this deal only
- request content type: multipart/form-data
- available only while deal status is pending_documents
- after upload, deal may automatically move to admin_review
  if both documents are uploaded or broker comment exists
"""

UPLOAD_PAYMENT_PROOF_DOC = """
Upload payment proof document for a deal.

Rules:
- authenticated broker of this deal only
- request content type: multipart/form-data
- available only while deal status is pending_documents
- after upload, deal may automatically move to admin_review
  if both documents are uploaded or broker comment exists
"""

BROKER_COMMENT_DOC = """
Add broker comment for a deal.

Rules:
- authenticated broker of this deal only
- available only while deal status is pending_documents
- if comment is added, deal may automatically move to admin_review
"""

ADMIN_APPROVE_DOC = """
Approve deal documents as admin.

Rules:
- admin only
- available only while deal status is admin_review

Effect:
- deal status changes to developer_confirm
- notifications are sent to developer and broker
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

DEVELOPER_CONFIRM_DOC = """
Confirm deal as developer.

Rules:
- authenticated developer of this deal only
- available only while deal status is developer_confirm

Effect:
- deal status changes to confirmed
- obligation status changes to fulfilled
- payment records are created
- broker is notified
"""

DEVELOPER_REJECT_DOC = """
Reject deal as developer.

Rules:
- authenticated developer of this deal only
- available only while deal status is developer_confirm
- rejection reason is required

Effect:
- deal status changes back to pending_documents
- developer rejection reason is saved
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
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="pending_documents | admin_review | developer_confirm | confirmed",
        ),
        OpenApiParameter(
            "obligation_status",
            OpenApiTypes.STR,
            required=False,
            description="active | fulfilled | overdue",
        ),
        OpenApiParameter("auction_id", OpenApiTypes.INT, required=False),
        OpenApiParameter("page", OpenApiTypes.INT, required=False),
        OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
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

deal_admin_approve_schema = extend_schema(
    summary="Approve deal as admin",
    description=ADMIN_APPROVE_DOC,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Deal approved and forwarded to developer.",
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

deal_developer_confirm_schema = extend_schema(
    summary="Confirm deal as developer",
    description=DEVELOPER_CONFIRM_DOC,
    responses={
        200: OpenApiResponse(
            response=DetailMessageSerializer,
            description="Deal confirmed and payments created.",
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

deal_developer_reject_schema = extend_schema(
    summary="Reject deal as developer",
    description=DEVELOPER_REJECT_DOC,
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
            description="Forbidden.",
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
