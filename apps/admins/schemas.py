# apps/admins/schemas.py
from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers

from .serializers import PendingPropertySerializer, UserActiveUpdateSerializer

broker_verify_schema = extend_schema(
    tags=["Admin"],
    summary="Verify or reject broker",
    description=(
        "Admin endpoint to accept/reject broker verification.\n\n"
        "Request:\n"
        "- id: broker user id\n"
        "- action: accept | reject\n\n"
        "Response:\n"
        "- message: human readable result\n"
        "- broker_user_id: id from request\n"
        "- status: accepted | rejected\n"
    ),
    request=inline_serializer(
        name="BrokerVerifyRequest",
        fields={
            "id": serializers.IntegerField(min_value=1),
            "action": serializers.ChoiceField(choices=["accept", "reject"]),
        },
    ),
    responses={
        200: inline_serializer(
            name="BrokerVerifyResponse",
            fields={
                "message": serializers.CharField(),
                "broker_user_id": serializers.IntegerField(),
                "status": serializers.ChoiceField(choices=["accepted", "rejected"]),
            },
        ),
        400: OpenApiResponse(
            description="Bad Request (invalid action / broker profile missing / validation error)"
        ),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Not Found (user not found or not broker)"),
    },
)


user_list_schema = extend_schema(
    tags=["Admin"],
    summary="List users",
    description=(
        "Admin list of users with optional broker/developer nested info.\n\n"
        "Supports:\n"
        "- filtering via UserFilter\n"
        "- ordering via ?ordering=\n"
        "- pagination (default DRF pagination)\n"
    ),
    parameters=[
        # Common filters (если у тебя UserFilter поддерживает больше — добавь сюда)
        OpenApiParameter(
            name="search",
            required=False,
            type=str,
            description="Search by email / name (if enabled).",
        ),
        OpenApiParameter(
            name="email",
            required=False,
            type=str,
            description="Filter by exact email (if enabled).",
        ),
        OpenApiParameter(
            name="role",
            required=False,
            type=str,
            description="Filter by role: developer|broker|admin",
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
            name="page", required=False, type=int, description="Page number"
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
            name="PaginatedUserListResponse",
            fields={
                "count": serializers.IntegerField(),
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": serializers.ListField(
                    child=inline_serializer(
                        name="UserListItem",
                        fields={
                            "id": serializers.IntegerField(),
                            "email": serializers.EmailField(),
                            "first_name": serializers.CharField(allow_blank=True),
                            "last_name": serializers.CharField(allow_blank=True),
                            "role": serializers.CharField(),
                            "is_active": serializers.BooleanField(),
                            "is_staff": serializers.BooleanField(),
                            "date_joined": serializers.DateTimeField(),
                            "broker": inline_serializer(
                                name="UserListBrokerInfo",
                                fields={
                                    "id": serializers.IntegerField(),
                                    "is_verified": serializers.BooleanField(),
                                    "verification_status": serializers.CharField(),
                                    "verified_at": serializers.DateTimeField(
                                        allow_null=True
                                    ),
                                    "rejected_at": serializers.DateTimeField(
                                        allow_null=True
                                    ),
                                    "inn_number": serializers.CharField(),
                                },
                            ),
                            "developer": inline_serializer(
                                name="UserListDeveloperInfo",
                                fields={
                                    "id": serializers.IntegerField(),
                                    "company_name": serializers.CharField(),
                                },
                            ),
                        },
                    )
                ),
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
            name="page", required=False, type=int, description="Page number"
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
        "Idempotent:\n"
        "- If status is pending -> becomes approved\n"
        "- Otherwise returns a message that it's already in current status"
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="ApprovePropertyResponse",
            fields={
                "message": serializers.CharField(),
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
        "Idempotent:\n"
        "- If status is pending -> becomes rejected\n"
        "- Otherwise returns a message that it's already in current status"
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="RejectPropertyResponse",
            fields={
                "message": serializers.CharField(),
            },
        ),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden (admin only)"),
        404: OpenApiResponse(description="Not Found (property not found)"),
    },
)
