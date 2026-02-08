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
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
    BidCreateSerializer,
    BidSerializer,
    SelectWinnerSerializer,
)

# If you already have a shared DRF "detail" error serializer, import it here.
# Otherwise this fallback keeps schema generation working.
try:
    from core.serializers import DRFDetailErrorSerializer  # type: ignore
except Exception:  # pragma: no cover

    class DRFDetailErrorSerializer(serializers.Serializer):
        detail = serializers.CharField()


# ----------------------------
# Docs (optional text blobs)
# ----------------------------

AUCTION_LIST_DOC = """
Returns a paginated list of auctions.

Filters:
- mode: open | closed
- status: draft | active | finished | cancelled
- property_id / propertyId: filter by property
- owner_id: filter by developer (auction owner)
- active=true: active auctions right now (status=active and start<=now<end)
- starts_before / starts_after: ISO datetime filters for start_date
- ends_before / ends_after: ISO datetime filters for end_date

Ordering:
- ordering: created_at, start_date, end_date, current_price, bids_count (prefix with '-' for desc)

Pagination:
- page, page_size
"""

AUCTION_CREATE_DOC = """
Create an auction.

Only authenticated developers can create auctions.
property_id must belong to the current developer.
"""

AUCTION_DETAIL_DOC = """
Return auction details.
For OPEN auctions, last 50 bids are public.
For CLOSED auctions, bids are visible only to auction owner.
"""

MY_AUCTIONS_DOC = """
Return auctions created by the current authenticated developer (owner=request.user).
Supports the same filters and ordering as the public list.
"""

AUCTION_BID_DOC = """
Place a bid for an auction.

Rules:
- auction must be ACTIVE and within start/end time
- broker must be authenticated (and optionally verified)
- amount must be >= min_price
- OPEN mode: amount must be strictly greater than current_price
"""

AUCTION_SELECT_WINNER_DOC = """
Select winner for CLOSED auction (manual).
Only auction owner (developer) can select winner, and only after end_date.
"""


# ----------------------------
# Schemas
# ----------------------------

auction_list_schema = extend_schema(
    summary="List auctions",
    description=AUCTION_LIST_DOC,
    parameters=[
        OpenApiParameter(
            "mode", OpenApiTypes.STR, required=False, description="open|closed"
        ),
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="draft|active|finished|cancelled",
        ),
        OpenApiParameter(
            "property_id",
            OpenApiTypes.INT,
            required=False,
            description="Filter by property id",
        ),
        OpenApiParameter(
            "propertyId",
            OpenApiTypes.INT,
            required=False,
            description="Filter by property id (camelCase)",
        ),
        OpenApiParameter(
            "owner_id",
            OpenApiTypes.INT,
            required=False,
            description="Filter by auction owner id",
        ),
        OpenApiParameter(
            "active",
            OpenApiTypes.BOOL,
            required=False,
            description="If true: only active auctions now",
        ),
        OpenApiParameter("starts_before", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("starts_after", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("ends_before", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("ends_after", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter(
            "ordering", OpenApiTypes.STR, required=False, description="e.g. -created_at"
        ),
        OpenApiParameter("page", OpenApiTypes.INT, required=False),
        OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
    ],
    responses={
        200: OpenApiResponse(
            response=AuctionListSerializer, description="Paginated auctions list."
        ),
    },
    tags=["Auctions"],
)

auction_create_schema = extend_schema(
    summary="Create auction",
    description=AUCTION_CREATE_DOC,
    request=AuctionCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=AuctionDetailSerializer, description="Auction created."
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden (developer only)."
        ),
    },
    tags=["Auctions"],
)

auction_detail_schema = extend_schema(
    summary="Get auction detail",
    description=AUCTION_DETAIL_DOC,
    responses={
        200: OpenApiResponse(
            response=AuctionDetailSerializer, description="Auction detail."
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Auctions"],
)

my_auctions_schema = extend_schema(
    summary="List my auctions",
    description=MY_AUCTIONS_DOC,
    parameters=[
        OpenApiParameter(
            "mode", OpenApiTypes.STR, required=False, description="open|closed"
        ),
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="draft|active|finished|cancelled",
        ),
        OpenApiParameter("property_id", OpenApiTypes.INT, required=False),
        OpenApiParameter("propertyId", OpenApiTypes.INT, required=False),
        OpenApiParameter("active", OpenApiTypes.BOOL, required=False),
        OpenApiParameter("starts_before", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("starts_after", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("ends_before", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("ends_after", OpenApiTypes.DATETIME, required=False),
        OpenApiParameter("ordering", OpenApiTypes.STR, required=False),
        OpenApiParameter("page", OpenApiTypes.INT, required=False),
        OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
    ],
    responses={
        200: OpenApiResponse(
            response=AuctionListSerializer,
            description="Paginated list of current developer auctions.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden (developer only)."
        ),
    },
    tags=["Auctions"],
)

# Response for POST /auctions/:id/bid is a dict: { auction: ..., bid: ... }
auction_bid_response_schema = inline_serializer(
    name="AuctionBidCreateResponse",
    fields={
        "auction": AuctionDetailSerializer(),
        "bid": BidSerializer(),
    },
)

auction_bid_schema = extend_schema(
    summary="Place a bid",
    description=AUCTION_BID_DOC,
    request=BidCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=auction_bid_response_schema, description="Bid created."
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden (broker only)."
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Auctions"],
)

auction_select_winner_schema = extend_schema(
    summary="Select winner (closed auction)",
    description=AUCTION_SELECT_WINNER_DOC,
    request=SelectWinnerSerializer,
    responses={
        200: OpenApiResponse(
            response=AuctionDetailSerializer, description="Winner selected."
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden (owner only)."
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Auctions"],
)
