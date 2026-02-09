from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .filters import AuctionFilter
from .models import Auction
from .paginations import AuctionPagination
from .permissions import IsAuctionOwnerOrAdmin, IsDeveloper
from .schemas import (
    auction_create_schema,
    auction_detail_schema,
    auction_list_schema,
    my_auctions_schema,
)
from .serializers import (
    AuctionCreateSerializer,
    AuctionDetailSerializer,
    AuctionListSerializer,
)
from .tasks import cancel_auction_status_tasks


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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auction = serializer.save()

        out_ser = AuctionDetailSerializer(auction, context={"request": request})
        return Response(out_ser.data, status=status.HTTP_201_CREATED)


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

    @auction_detail_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AuctionCancelView(generics.DestroyAPIView):
    serializer_class = AuctionDetailSerializer
    http_method_names = ["delete", "head", "options"]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), IsAuctionOwnerOrAdmin()]
        return [AllowAny()]

    def get_queryset(self):
        return Auction.objects.exclude(
            Q(status=Auction.Status.CANCELLED) | Q(status=Auction.Status.FINISHED)
        ).only(
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

    def perform_destroy(self, instance: Auction) -> None:
        """
        Soft cancel: set status=CANCELLED and remove scheduled beat tasks.
        Cancellation rules:
        - after start_date: nobody can cancel
        - within 10 minutes before start_date: only admin can cancel
        """
        user = self.request.user
        is_admin = bool(
            getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
        )
        now = timezone.now()

        with transaction.atomic():
            # Lock row to avoid races with beat tasks and concurrent deletes
            auction = Auction.objects.select_for_update().get(pk=instance.pk)

            # After start: cancellation is forbidden for everyone (including admin)
            if now >= auction.start_date:
                raise ValidationError(
                    {"detail": "Auction cannot be cancelled after it has started."}
                )

            # Within 10 minutes before start: only admin can cancel
            if auction.start_date - now <= timedelta(minutes=10) and not is_admin:
                raise PermissionDenied(
                    "Only admin can cancel an auction within 10 minutes of its start."
                )

            auction.status = Auction.Status.CANCELLED
            auction.save(update_fields=["status", "updated_at"])

            # Remove beat tasks after DB commit
            transaction.on_commit(
                lambda: cancel_auction_status_tasks(auction_id=auction.id)
            )

    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)
