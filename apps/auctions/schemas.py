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
    BidUpdateSerializer,
    ClosedSelectWinnerSerializer,
    ClosedShortlistSerializer,
    ParticipantsListSerializer,
)


# Fallback detail serializer for errors
class DRFDetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


AUCTION_LIST_DOC = """
List auctions.

Filters:
- mode: open | closed
- status: scheduled | active | finished | cancelled
- property_id / propertyId
- owner_id
- active=true (status=active and start<=now<end)
- starts_before / starts_after (ISO datetime)
- ends_before / ends_after (ISO datetime)

Ordering:
- ordering: created_at, start_date, end_date, current_price, bids_count (prefix '-' for desc)

Pagination:
- page, page_size
"""

AUCTION_CREATE_DOC = """
Create an auction.

Only authenticated developers can create auctions.
property_id must belong to current developer.
Auction is created as SCHEDULED; Celery beat will activate at start_date.

Rules for pricing:
- min_price: minimum acceptable bid amount for the auction
- OPEN auction: min_bid_increment is required and must be >= 1
- CLOSED auction: min_bid_increment must be null / omitted
"""

AUCTION_DETAIL_DOC = """
Auction details.

OPEN: last 50 bids are public.
CLOSED: bids are visible only to owner/admin (via /sealed-bids/ endpoint).

Fields:
- min_price: auction minimum price
- min_bid_increment: open-auction minimum increment, null for closed auctions
"""

AUCTION_CANCEL_DOC = """
Cancel auction (soft-cancel).

Rules:
- After start_date: nobody can cancel (even admin).
- Within AUCTION_CANCEL_LOCK_BEFORE_START: only admin can cancel.
- Earlier: owner or admin can cancel.
"""

JOIN_DOC = """
Join an auction as a participant (stored in Redis).
Required to place bids (both OPEN WS bids and CLOSED HTTP bids).
"""

PARTICIPANTS_DOC = """
Get auction participants list (Redis).
OPEN: brokers can see.
CLOSED: only owner/admin can see.
"""

CLOSED_BID_CREATE_DOC = """
Place a sealed bid for CLOSED auction (HTTP).

Rules:
- auction must be ACTIVE and within time window
- broker must be participant (joined)
- one bid per broker (sealed)
- amount >= min_price
"""

CLOSED_BID_UPDATE_DOC = """
Update your sealed bid for CLOSED auction while ACTIVE.

Rules:
- auction must be ACTIVE and within time window
- broker must be participant (joined)
- updates own bid only
- amount >= min_price
"""

SEALED_BIDS_LIST_DOC = """
List sealed bids for CLOSED auction.

Visible only to owner/admin.
"""

CLOSED_SHORTLIST_DOC = """
Owner/admin sets shortlist of bid ids after auction is FINISHED (CLOSED).
"""

CLOSED_SELECT_WINNER_DOC = """
Owner/admin selects winner bid from shortlist after auction is FINISHED (CLOSED).
"""


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
            description="scheduled|active|finished|cancelled",
        ),
        OpenApiParameter("property_id", OpenApiTypes.INT, required=False),
        OpenApiParameter("propertyId", OpenApiTypes.INT, required=False),
        OpenApiParameter("owner_id", OpenApiTypes.INT, required=False),
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
            response=AuctionListSerializer, description="Paginated auctions list."
        )
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
        )
    },
    tags=["Auctions"],
)

my_auctions_schema = extend_schema(
    summary="List my auctions",
    description=(
        "Developer-only list of own auctions. "
        "Supports same filters, ordering and pagination as public list."
    ),
    parameters=[
        OpenApiParameter(
            "mode", OpenApiTypes.STR, required=False, description="open|closed"
        ),
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="scheduled|active|finished|cancelled",
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
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
    },
    tags=["Auctions"],
)

auction_cancel_schema = extend_schema(
    summary="Cancel auction",
    description=AUCTION_CANCEL_DOC,
    responses={
        204: OpenApiResponse(description="Auction cancelled."),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Auctions"],
)

join_schema = extend_schema(
    summary="Join auction",
    description=JOIN_DOC,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="JoinAuctionResponse",
                fields={
                    "auction_id": serializers.IntegerField(),
                    "user_id": serializers.IntegerField(),
                    "participants_count": serializers.IntegerField(),
                },
            )
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
    },
    tags=["Participants"],
)

participants_list_schema = extend_schema(
    summary="List participants",
    description=PARTICIPANTS_DOC,
    responses={
        200: OpenApiResponse(
            response=ParticipantsListSerializer, description="Participants list."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Participants"],
)

closed_bid_create_schema = extend_schema(
    summary="Place sealed bid (CLOSED)",
    description=CLOSED_BID_CREATE_DOC,
    request=BidCreateSerializer,
    responses={
        201: OpenApiResponse(response=BidSerializer, description="Bid created."),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
    },
    tags=["Bids (Closed)"],
)

closed_bid_update_schema = extend_schema(
    summary="Update my sealed bid (CLOSED)",
    description=CLOSED_BID_UPDATE_DOC,
    request=BidUpdateSerializer,
    responses={
        200: OpenApiResponse(response=BidSerializer, description="Bid updated."),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Validation error."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
    },
    tags=["Bids (Closed)"],
)

sealed_bids_list_schema = extend_schema(
    summary="List sealed bids (CLOSED) for owner/admin",
    description=SEALED_BIDS_LIST_DOC,
    responses={
        200: OpenApiResponse(response=BidSerializer, description="List of bids."),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
    },
    tags=["Bids (Closed)"],
)

closed_shortlist_schema = extend_schema(
    summary="Set shortlist (CLOSED)",
    description=CLOSED_SHORTLIST_DOC,
    request=ClosedShortlistSerializer,
    responses={
        200: OpenApiResponse(description="Shortlist set."),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
    },
    tags=["Closed Flow"],
)

closed_select_winner_schema = extend_schema(
    summary="Select winner from shortlist (CLOSED)",
    description=CLOSED_SELECT_WINNER_DOC,
    request=ClosedSelectWinnerSerializer,
    responses={
        200: OpenApiResponse(description="Winner selected."),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
    },
    tags=["Closed Flow"],
)
