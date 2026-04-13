from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers

from apps.users.serializers import TokenUserSerializer

from .serializers import (
    AdminDeveloperCreateSerializer,
    AdminDeveloperUpdateSerializer,
    PendingPropertySerializer,
    UserActiveUpdateSerializer,
)

broker_verify_schema = extend_schema(
    tags=["Admin"],
    summary="Verify or reject broker",
    description=(
        "Admin endpoint to accept or reject broker verification.\n\n"
        "Request:\n"
        "- id: broker user id\n"
        "- action: accept | reject\n"
        "- reason: required when action=reject\n\n"
        "Behavior:\n"
        "- accept: broker becomes verified and rejection reason is cleared\n"
        "- reject: broker becomes rejected and rejection reason is saved\n\n"
        "Response:\n"
        "- message: human readable result\n"
        "- broker_id: broker id\n"
        "- verification_status: pending | accepted | rejected\n"
        "- is_verified: current verification flag\n"
        "- verified_at: datetime when accepted\n"
        "- rejected_at: datetime when rejected\n"
        "- rejection_reason: saved rejection reason or null\n"
    ),
    request=inline_serializer(
        name="BrokerVerifyRequest",
        fields={
            "id": serializers.IntegerField(min_value=1),
            "action": serializers.ChoiceField(choices=["accept", "reject"]),
            "reason": serializers.CharField(
                required=False,
                allow_blank=False,
                max_length=1000,
                help_text="Required when action=reject",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="BrokerVerifyResponse",
            fields={
                "message": serializers.CharField(),
                "broker_id": serializers.IntegerField(),
                "verification_status": serializers.ChoiceField(
                    choices=["pending", "accepted", "rejected"]
                ),
                "is_verified": serializers.BooleanField(),
                "verified_at": serializers.DateTimeField(allow_null=True),
                "rejected_at": serializers.DateTimeField(allow_null=True),
                "rejection_reason": serializers.CharField(
                    allow_null=True,
                    required=False,
                ),
            },
        ),
        400: OpenApiResponse(
            description="Bad Request (validation error, reason missing for reject, or broker profile missing)"
        ),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Not Found (user not found or not broker)"),
    },
)


user_list_schema = extend_schema(
    tags=["Admin"],
    summary="List users",
    description=(
        "Admin list of users with optional broker/developer nested info and user documents.\n\n"
        "Supports:\n"
        "- filtering via UserFilter\n"
        "- ordering via ?ordering=\n"
        "- pagination\n\n"
        "Note:\n"
        "- Documents belong to the user.\n"
        "- Admin users should return an empty documents list.\n"
    ),
    parameters=[
        OpenApiParameter(
            name="search",
            required=False,
            type=str,
            description="Search by email / name (only if supported by UserFilter).",
        ),
        OpenApiParameter(
            name="email",
            required=False,
            type=str,
            description="Filter by exact email (only if supported by UserFilter).",
        ),
        OpenApiParameter(
            name="role",
            required=False,
            type=str,
            description="Filter by role: developer | broker | admin",
        ),
        OpenApiParameter(
            name="is_active",
            required=False,
            type=bool,
            description="Filter by active status",
        ),
        OpenApiParameter(
            name="ordering",
            required=False,
            type=str,
            description="Ordering fields: date_joined, email, role, is_active. Example: -date_joined",
        ),
        OpenApiParameter(
            name="page",
            required=False,
            type=int,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            required=False,
            type=int,
            description="Items per page (if enabled by paginator)",
        ),
    ],
    responses={
        200: inline_serializer(
            name="PaginatedUserListResponse",
            fields={
                "count": serializers.IntegerField(),
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": TokenUserSerializer(many=True),
            },
        ),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
    },
)


UserActiveUpdateResponseSerializer = inline_serializer(
    name="UserActiveUpdateResponse",
    fields={
        "id": serializers.IntegerField(),
        "is_active": serializers.BooleanField(),
        "message": serializers.CharField(),
    },
)


user_active_update_schema = extend_schema(
    tags=["Admin"],
    summary="Block / unblock user",
    description="Admin-only. Updates user's is_active flag.",
    request=UserActiveUpdateSerializer,
    responses={
        200: OpenApiResponse(response=UserActiveUpdateResponseSerializer),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="User not found"),
    },
)

AdminDeveloperResponseSerializer = inline_serializer(
    name="AdminDeveloperResponse",
    fields={
        "message": serializers.CharField(),
        "user": TokenUserSerializer(),
    },
)


admin_developer_create_schema = extend_schema(
    tags=["Admin"],
    summary="Create developer",
    description=(
        "Admin-only endpoint to create a developer account.\n\n"
        "Behavior:\n"
        "- creates User with role=developer\n"
        "- creates related Developer profile with company_name\n"
        "- returns created user payload"
    ),
    request=AdminDeveloperCreateSerializer,
    responses={
        201: OpenApiResponse(response=AdminDeveloperResponseSerializer),
        400: OpenApiResponse(description="Validation error"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        409: OpenApiResponse(description="User already exists"),
    },
)


admin_developer_update_schema = extend_schema(
    tags=["Admin"],
    summary="Update developer",
    description=(
        "Admin-only endpoint to update a developer account.\n\n"
        "Updatable fields:\n"
        "- email\n"
        "- first_name\n"
        "- last_name\n"
        "- company_name\n\n"
        "Path param `pk` is developer user id."
    ),
    request=AdminDeveloperUpdateSerializer,
    responses={
        200: OpenApiResponse(response=AdminDeveloperResponseSerializer),
        400: OpenApiResponse(description="Validation error"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Developer not found"),
        409: OpenApiResponse(description="User already exists"),
    },
)


pending_properties_list_schema = extend_schema(
    tags=["Admin"],
    summary="List pending properties",
    description=(
        "Admin list of properties on moderation.\n\n"
        "Returns only properties with moderation_status = pending.\n"
        "Pagination: default DRF pagination."
    ),
    parameters=[
        OpenApiParameter(
            name="page",
            required=False,
            type=int,
            description="Page number",
        ),
        OpenApiParameter(
            name="page_size",
            required=False,
            type=int,
            description="Items per page (if enabled)",
        ),
    ],
    responses={
        200: inline_serializer(
            name="PaginatedPendingPropertyListResponse",
            fields={
                "count": serializers.IntegerField(),
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": PendingPropertySerializer(many=True),
            },
        ),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
    },
)


approve_property_schema = extend_schema(
    tags=["Admin"],
    summary="Approve property",
    description=(
        "Admin-only. Approves property moderation.\n\n"
        "Behavior:\n"
        "- property moderation_status becomes approved\n"
        "- moderation_rejection_reason is cleared\n\n"
        "Idempotent:\n"
        "- if already approved, returns current state without error"
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="ApprovePropertyResponse",
            fields={
                "message": serializers.CharField(),
                "property_id": serializers.IntegerField(),
                "moderation_status": serializers.ChoiceField(
                    choices=["pending", "approved", "rejected"]
                ),
                "moderation_rejection_reason": serializers.CharField(
                    allow_null=True,
                    required=False,
                ),
            },
        ),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Not Found (property not found)"),
    },
)


reject_property_schema = extend_schema(
    tags=["Admin"],
    summary="Reject property",
    description=(
        "Admin-only. Rejects property moderation.\n\n"
        "Request:\n"
        "- reason: required rejection reason\n\n"
        "Behavior:\n"
        "- property moderation_status becomes rejected\n"
        "- moderation_rejection_reason is saved\n\n"
        "Idempotent:\n"
        "- if already rejected, returns current state without error"
    ),
    request=inline_serializer(
        name="RejectPropertyRequest",
        fields={
            "reason": serializers.CharField(
                required=True,
                allow_blank=False,
                max_length=1000,
                help_text="Required rejection reason",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="RejectPropertyResponse",
            fields={
                "message": serializers.CharField(),
                "property_id": serializers.IntegerField(),
                "moderation_status": serializers.ChoiceField(
                    choices=["pending", "approved", "rejected"]
                ),
                "moderation_rejection_reason": serializers.CharField(),
            },
        ),
        400: OpenApiResponse(description="Bad Request (reason is required)"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Not Found (property not found)"),
    },
)
