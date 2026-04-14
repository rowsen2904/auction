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
    AuctionAssignSerializer,
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
    AuctionSelectWinnersSerializer,
    BidCreateSerializer,
    BidSerializer,
    BidUpdateSerializer,
    ClosedShortlistSerializer,
    ParticipantsListSerializer,
)


class DRFDetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


AUCTION_LIST_DOC = """
List auctions.

Filters:
- mode: open | closed
- status: scheduled | active | finished | cancelled
- propertyId
- ownerId
- active=true (status=active and start<=now<end)
- starts_before / starts_after (ISO datetime)
- ends_before / ends_after (ISO datetime)

Ordering:
- ordering: created_at, start_date, end_date, current_price, bids_count
  (prefix '-' for desc)

Pagination:
- page, page_size

Notes:
- OPEN auction has exactly one property.
- CLOSED auction may contain one or many properties in a single lot.
- response includes:
  - real_property (backward compatibility / OPEN flow)
  - properties[] (lot-aware response)
  - lot_total_price
"""

AUCTION_CREATE_DOC = """
Create an auction.

Only authenticated developers can create auctions.

Request supports:
- propertyIds: int[]  (current contract)
- propertyId: int     (backward compatibility for single property)

Rules:
- OPEN: exactly one property must be selected
- CLOSED: one or many properties may be selected
- selected properties must belong to current developer
- selected properties must be approved and published
- selected properties must not already be linked to a blocking auction
- CLOSED lot properties must be mutually compatible
- auction is created as SCHEDULED
- background tasks activate/finish auction by dates

Pricing rules:
- min_price is for the whole auction / lot
- OPEN requires min_bid_increment >= 1
- CLOSED forces min_bid_increment = null
"""

AUCTION_DETAIL_DOC = """
Auction details.

OPEN:
- one property
- public/open bid history in response
- winner is determined automatically by highest bid on finish

CLOSED:
- one or many properties inside a lot
- sealed bids are placed for the whole lot
- bids are visible only to owner/admin in detail response
- authenticated broker also receives own bid in `myBid`
- after finish, developer may:
  1) shortlist bids
  2) select one or many winning brokers
  3) assign properties to selected winners
  4) create deals per broker-property pair

Fields:
- min_price: minimum price for whole lot
- min_bid_increment: open-only increment, null for closed
- properties: array of lot properties
- lot_total_price: sum of property prices in the lot
"""

AUCTION_CANCEL_DOC = """
Cancel auction (soft-cancel).

Rules:
- After start_date: nobody can cancel.
- Within AUCTION_CANCEL_LOCK_BEFORE_START: only admin can cancel.
- Earlier: owner or admin can cancel.
"""

JOIN_DOC = """
Join an auction as a participant.
"""

PARTICIPANTS_DOC = """
Get auction participants list.

OPEN:
- visible according to current backend rules

CLOSED:
- only owner/admin can see participants
"""

CLOSED_BID_CREATE_DOC = """
Place a sealed bid for CLOSED auction (HTTP).

Rules:
- auction must be ACTIVE and inside active time window
- broker must be verified
- owner cannot bid on own auction
- one sealed bid per broker per auction
- amount must be >= 0.01

Note:
- bid is for the WHOLE LOT, not for a single property.
"""

CLOSED_BID_UPDATE_DOC = """
Update your sealed bid for CLOSED auction while ACTIVE.

Rules:
- only own sealed bid can be updated
- amount must remain >= 0.01
- broker must be verified
- owner cannot bid
- deleting/cancelling sealed bid is not allowed by current business flow
"""

SEALED_BIDS_LIST_DOC = """
List sealed bids for CLOSED auction.

Visible only to owner/admin.
"""

CLOSED_SHORTLIST_DOC = """
Set shortlist of sealed bid ids for CLOSED auction after it is FINISHED.
"""

AUCTION_SELECT_WINNERS_DOC = """
Select one or many winning brokers for CLOSED auction after it is FINISHED.

Request:
- brokerIds: list[int]

Behavior:
- selected winners are stored for further assignment step
- this step DOES NOT create deals yet
"""

AUCTION_ASSIGN_DOC = """
Assign lot properties to selected winning brokers and create deals.

Request:
{
  "assignments": [
    {"brokerId": 10, "propertyIds": [1, 2]},
    {"brokerId": 11, "propertyIds": [3]}
  ]
}

Validation:
- all propertyIds must belong to this auction
- all brokerIds must be among selected winners
- each property must be assigned exactly once
- deals are created per broker-property pair
"""

CLOSED_SELECT_WINNER_DOC = """
Backward-compatible schema name for the current select-winner endpoint.

Important:
- current request uses brokerIds[]
- it behaves as multi-winner selection step for CLOSED auction
- deals are NOT created here
"""


auction_list_schema = extend_schema(
    summary="List auctions",
    description=AUCTION_LIST_DOC,
    parameters=[
        OpenApiParameter(
            "mode", OpenApiTypes.STR, required=False, description="open | closed"
        ),
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="scheduled | active | finished | cancelled",
        ),
        OpenApiParameter("propertyId", OpenApiTypes.INT, required=False),
        OpenApiParameter("ownerId", OpenApiTypes.INT, required=False),
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
            description="Paginated auctions list.",
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
            response=AuctionDetailSerializer,
            description="Auction created.",
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
            description="Forbidden (developer only).",
        ),
    },
    tags=["Auctions"],
)

auction_detail_schema = extend_schema(
    summary="Get auction detail",
    description=AUCTION_DETAIL_DOC,
    responses={
        200: OpenApiResponse(
            response=AuctionDetailSerializer,
            description="Auction detail.",
        ),
        404: OpenApiResponse(description="Auction not found."),
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
            "mode", OpenApiTypes.STR, required=False, description="open | closed"
        ),
        OpenApiParameter(
            "status",
            OpenApiTypes.STR,
            required=False,
            description="scheduled | active | finished | cancelled",
        ),
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
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden.",
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
            ),
            description="Joined / already joined auction.",
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
    },
    tags=["Participants"],
)

participants_list_schema = extend_schema(
    summary="List participants",
    description=PARTICIPANTS_DOC,
    responses={
        200: OpenApiResponse(
            response=ParticipantsListSerializer,
            description="Participants list.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden.",
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
        404: OpenApiResponse(description="Auction not found."),
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
        404: OpenApiResponse(description="Bid or auction not found."),
    },
    tags=["Bids (Closed)"],
)

sealed_bids_list_schema = extend_schema(
    summary="List sealed bids (CLOSED) for owner/admin",
    description=SEALED_BIDS_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=BidSerializer, description="List of sealed bids."
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Unauthorized."
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer, description="Forbidden."
        ),
        404: OpenApiResponse(description="Auction not found."),
    },
    tags=["Bids (Closed)"],
)

closed_shortlist_schema = extend_schema(
    summary="Set shortlist (CLOSED)",
    description=CLOSED_SHORTLIST_DOC,
    request=ClosedShortlistSerializer,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="ClosedShortlistResponse",
                fields={
                    "shortlistedBidIds": serializers.ListField(
                        child=serializers.IntegerField()
                    ),
                },
            ),
            description="Shortlist set.",
        ),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
        404: OpenApiResponse(description="Auction not found."),
    },
    tags=["Closed Flow"],
)

auction_select_winners_schema = extend_schema(
    summary="Select winners (CLOSED)",
    description=AUCTION_SELECT_WINNERS_DOC,
    request=AuctionSelectWinnersSerializer,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="AuctionSelectWinnersResponse",
                fields={
                    "auctionId": serializers.IntegerField(),
                    "selectedBrokerIds": serializers.ListField(
                        child=serializers.IntegerField()
                    ),
                    "selectedBidIds": serializers.ListField(
                        child=serializers.IntegerField()
                    ),
                },
            ),
            description="Winning brokers selected.",
        ),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
        404: OpenApiResponse(description="Auction not found."),
    },
    tags=["Closed Flow"],
)

auction_assign_schema = extend_schema(
    summary="Assign properties to winners (CLOSED)",
    description=AUCTION_ASSIGN_DOC,
    request=AuctionAssignSerializer,
    responses={
        201: OpenApiResponse(
            response=inline_serializer(
                name="AuctionAssignResponse",
                fields={
                    "auctionId": serializers.IntegerField(),
                    "dealsCount": serializers.IntegerField(),
                    "dealIds": serializers.ListField(child=serializers.IntegerField()),
                },
            ),
            description="Deals created after property assignment.",
        ),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
        404: OpenApiResponse(description="Auction not found."),
    },
    tags=["Closed Flow"],
)

closed_select_winner_schema = extend_schema(
    summary="Select winner(s) from shortlist (CLOSED)",
    description=CLOSED_SELECT_WINNER_DOC,
    request=AuctionSelectWinnersSerializer,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="ClosedSelectWinnerResponse",
                fields={
                    "auctionId": serializers.IntegerField(),
                    "selectedBrokerIds": serializers.ListField(
                        child=serializers.IntegerField()
                    ),
                    "selectedBidIds": serializers.ListField(
                        child=serializers.IntegerField()
                    ),
                },
            ),
            description="Winner selection stored.",
        ),
        400: OpenApiResponse(response=DRFDetailErrorSerializer),
        401: OpenApiResponse(response=DRFDetailErrorSerializer),
        403: OpenApiResponse(response=DRFDetailErrorSerializer),
        404: OpenApiResponse(description="Auction not found."),
    },
    tags=["Closed Flow"],
)
