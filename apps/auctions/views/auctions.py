from __future__ import annotations

from auctions.filters import AuctionFilter
from auctions.models import Auction
from auctions.paginations import AuctionPagination
from auctions.permissions import IsBroker, IsDeveloper
from auctions.schemas import (
    auction_create_schema,
    auction_detail_schema,
    auction_list_schema,
    auction_select_winners_schema,
    my_auctions_schema,
    participated_auctions_schema,
)
from auctions.serializers import (
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
    AuctionSelectWinnerSerializer,
)
from auctions.services.assignments import select_closed_auction_winner
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _auction_base_queryset():
    return (
        Auction.objects.select_related(
            "owner",
            "real_property",
            "winner_bid",
            "winner_bid__broker",
        )
        .prefetch_related(
            "properties",
            "shortlisted_bids",
        )
        .order_by("-created_at")
    )


def _hide_drafts_from_strangers(qs, user):
    """
    Drafts are private to their owner and to admins. Anyone else asking
    the public/broker views should not see them.
    """
    from django.db.models import Q

    if not user or not getattr(user, "is_authenticated", False):
        return qs.exclude(status=Auction.Status.DRAFT)
    is_admin = bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_admin", False)
    )
    if is_admin:
        return qs
    return qs.filter(
        ~Q(status=Auction.Status.DRAFT) | Q(owner=user)
    )


class MyAuctionListView(generics.ListAPIView):
    pagination_class = AuctionPagination
    serializer_class = AuctionListSerializer
    permission_classes = [IsAuthenticated, IsDeveloper]
    filterset_class = AuctionFilter

    ordering = ["-created_at"]
    ordering_fields = [
        "created_at",
        "start_date",
        "end_date",
        "current_price",
        "bids_count",
    ]

    def get_queryset(self):
        return _auction_base_queryset().filter(owner=self.request.user)

    @my_auctions_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BrokerParticipatedAuctionsView(generics.ListAPIView):
    """Auctions in which the current broker has placed at least one bid."""

    pagination_class = AuctionPagination
    serializer_class = AuctionListSerializer
    permission_classes = [IsAuthenticated, IsBroker]
    filterset_class = AuctionFilter

    ordering = ["-created_at"]
    ordering_fields = [
        "created_at",
        "start_date",
        "end_date",
        "current_price",
        "bids_count",
    ]

    def get_queryset(self):
        return (
            _auction_base_queryset()
            .filter(bids__broker=self.request.user)
            .exclude(status=Auction.Status.DRAFT)
            .distinct()
        )

    @participated_auctions_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AuctionListCreateView(generics.ListCreateAPIView):
    pagination_class = AuctionPagination
    filterset_class = AuctionFilter

    ordering = ["-created_at"]
    ordering_fields = [
        "created_at",
        "start_date",
        "end_date",
        "current_price",
        "bids_count",
    ]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsDeveloper()]
        return [AllowAny()]

    def get_queryset(self):
        return _hide_drafts_from_strangers(
            _auction_base_queryset(), getattr(self.request, "user", None)
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AuctionCreateSerializer
        return AuctionListSerializer

    @auction_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @auction_create_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        auction = ser.save()

        auction = _auction_base_queryset().get(pk=auction.pk)
        out = AuctionDetailSerializer(auction, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)


class ActiveAuctionListCreateView(generics.ListAPIView):
    pagination_class = AuctionPagination
    filterset_class = AuctionFilter

    ordering = ["-created_at"]
    ordering_fields = [
        "created_at",
        "start_date",
        "end_date",
        "current_price",
        "bids_count",
    ]

    def get_permissions(self):
        return [AllowAny()]

    def get_queryset(self):
        # ACTIVE-only — never includes drafts by definition.
        return _auction_base_queryset().filter(status=Auction.Status.ACTIVE)

    def get_serializer_class(self):
        return AuctionListSerializer

    @auction_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AuctionDetailView(generics.RetrieveAPIView):
    serializer_class = AuctionDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return _hide_drafts_from_strangers(
            _auction_base_queryset(), getattr(self.request, "user", None)
        )

    @auction_detail_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AuctionSelectWinnerView(APIView):
    permission_classes = [IsAuthenticated, IsDeveloper]

    @auction_select_winners_schema
    def post(self, request, pk: int):
        serializer = AuctionSelectWinnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        auction = get_object_or_404(
            _auction_base_queryset(),
            pk=pk,
        )

        if auction.owner_id != request.user.id:
            raise PermissionDenied(
                "Только владелец аукциона может выбирать победителя."
            )

        bid = select_closed_auction_winner(
            auction=auction,
            broker_id=serializer.validated_data["broker_id"],
        )

        return Response(
            {
                "auctionId": auction.id,
                "selectedBrokerId": bid.broker_id,
                "selectedBidId": bid.id,
            },
            status=status.HTTP_200_OK,
        )
