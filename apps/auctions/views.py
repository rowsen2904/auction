from __future__ import annotations

from properties.permissions import IsDeveloper
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .filters import AuctionFilter
from .models import Auction
from .paginations import AuctionPagination
from .serializers import (
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
)


class MyAuctionListView(generics.ListAPIView):
    pagination_class = AuctionPagination
    serializer_class = AuctionListSerializer
    permission_classes = [IsAuthenticated, IsDeveloper]

    ordering = ["-created_at"]
    ordering_fields = [
        "created_at",
        "start_date",
        "end_date",
        "current_price",
        "bids_count",
    ]

    def get_queryset(self):
        print(self.request.user)
        return Auction.objects.filter(owner=self.request.user).only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auction = serializer.save()

        out_ser = AuctionDetailSerializer(auction, context={"request": request})
        return Response(out_ser.data, status=status.HTTP_201_CREATED)


class AuctionDetailView(generics.RetrieveAPIView):
    """
    GET /auctions/:id
    """

    serializer_class = AuctionDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Auction.objects.all().only(
            "id",
            "real_property_id",
            "owner_id",
            "mode",
            "min_price",
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

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx
