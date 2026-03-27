from __future__ import annotations

from auctions.filters import AuctionFilter
from auctions.models import Auction
from auctions.paginations import AuctionPagination
from auctions.permissions import IsDeveloper
from auctions.schemas import (
    auction_create_schema,
    auction_detail_schema,
    auction_list_schema,
    my_auctions_schema,
)
from auctions.serializers import (
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


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
        return Auction.objects.filter(owner=self.request.user).only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid_id",
            "created_at",
            "updated_at",
        )

    @my_auctions_schema
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
        return Auction.objects.all().only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid_id",
            "created_at",
            "updated_at",
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
        return Auction.objects.filter().only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid_id",
            "created_at",
            "updated_at",
        )

    def get_serializer_class(self):
        return AuctionListSerializer

    @auction_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AuctionDetailView(generics.RetrieveAPIView):
    serializer_class = AuctionDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Auction.objects.all().only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid_id",
            "created_at",
            "updated_at",
        )

    @auction_detail_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
