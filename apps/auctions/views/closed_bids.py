from __future__ import annotations

from decimal import Decimal

from auctions.models import Auction, Bid
from auctions.participants import add_participant
from auctions.permissions import IsBroker
from auctions.schemas import (
    closed_bid_create_schema,
    closed_bid_update_schema,
    sealed_bids_list_schema,
)
from auctions.serializers import BidCreateSerializer, BidSerializer, BidUpdateSerializer
from auctions.services.rules import (
    ctx_for,
    ensure_active_window,
    ensure_min_price,
    ensure_mode,
    ensure_not_owner,
    is_admin,
)
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class ClosedBidCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated, IsBroker]
    serializer_class = BidCreateSerializer

    @closed_bid_create_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        auction_id = int(kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount: Decimal = serializer.validated_data["amount"]

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().only(
                    "id",
                    "owner_id",
                    "mode",
                    "status",
                    "min_price",
                    "start_date",
                    "end_date",
                    "bids_count",
                    "current_price",
                    "highest_bid_id",
                ),
                pk=auction_id,
            )

            ctx = ctx_for(auction=auction, user=request.user)
            ensure_mode(
                ctx,
                allowed={Auction.Mode.CLOSED},
                message="HTTP bidding is allowed only for CLOSED auctions.",
            )
            ensure_active_window(ctx)
            ensure_not_owner(ctx)
            ensure_min_price(ctx, amount=amount)

            if Bid.objects.filter(
                auction_id=auction.id, broker_id=request.user.id, is_sealed=True
            ).exists():
                raise ValidationError(
                    {"detail": "You can place only one bid in a closed auction."}
                )

            bid = Bid.objects.create(
                auction_id=auction.id,
                broker=request.user,
                amount=amount,
                is_sealed=True,
            )

            # Auto-join on bid (если Redis доступен — join будет)
            try:
                add_participant(
                    auction_id=auction.id,
                    user_id=request.user.id,
                    end_date=auction.end_date,
                )
            except Exception:
                # Tests/local env may not have Redis backend
                pass

            auction.bids_count += 1
            if amount > auction.current_price:
                auction.current_price = amount
                auction.highest_bid_id = bid.id
            auction.save(
                update_fields=[
                    "bids_count",
                    "current_price",
                    "highest_bid_id",
                    "updated_at",
                ]
            )

        return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)


class MyClosedBidUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated, IsBroker]
    serializer_class = BidUpdateSerializer
    http_method_names = ["patch", "head", "options"]

    @closed_bid_update_schema
    def patch(self, request, *args, **kwargs):  # type: ignore[override]
        auction_id = int(kwargs["pk"])
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data.get("amount")
        if amount is None:
            raise ValidationError({"amount": "This field is required."})

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().only(
                    "id",
                    "owner_id",
                    "mode",
                    "status",
                    "min_price",
                    "start_date",
                    "end_date",
                    "current_price",
                    "highest_bid_id",
                ),
                pk=auction_id,
            )

            ctx = ctx_for(auction=auction, user=request.user)
            ensure_mode(
                ctx,
                allowed={Auction.Mode.CLOSED},
                message="HTTP bid update is allowed only for CLOSED auctions.",
            )
            ensure_active_window(ctx)
            ensure_not_owner(ctx)
            ensure_min_price(ctx, amount=amount)

            bid = get_object_or_404(
                Bid.objects.select_for_update().only(
                    "id", "amount", "auction_id", "broker_id", "is_sealed"
                ),
                auction_id=auction.id,
                broker_id=request.user.id,
                is_sealed=True,
            )

            old_amount = bid.amount
            bid.amount = amount
            bid.save(update_fields=["amount"])  # <-- IMPORTANT: no updated_at

            need_recalc = False
            if amount > auction.current_price:
                auction.current_price = amount
                auction.highest_bid_id = bid.id
            else:
                if auction.highest_bid_id == bid.id and amount < old_amount:
                    need_recalc = True

            if need_recalc:
                top = (
                    Bid.objects.filter(auction_id=auction.id, is_sealed=True)
                    .order_by("-amount", "-id")
                    .only("id", "amount")
                    .first()
                )
                if top:
                    auction.current_price = top.amount
                    auction.highest_bid_id = top.id
                else:
                    auction.current_price = Decimal("0.00")
                    auction.highest_bid_id = None

            auction.save(
                update_fields=["current_price", "highest_bid_id", "updated_at"]
            )

        return Response(BidSerializer(bid).data, status=status.HTTP_200_OK)


class ClosedBidsListForOwnerAdminView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BidSerializer

    @sealed_bids_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        auction_id = int(self.kwargs["pk"])
        auction = get_object_or_404(
            Auction.objects.only("id", "owner_id", "mode"), pk=auction_id
        )

        if auction.mode != Auction.Mode.CLOSED:
            raise ValidationError({"detail": "Only for CLOSED auctions."})

        if not (
            is_admin(self.request.user) or self.request.user.id == auction.owner_id
        ):
            raise PermissionDenied("Only owner/admin can view sealed bids.")

        return (
            Bid.objects.filter(auction_id=auction.id, is_sealed=True)
            .select_related("broker")
            .only("id", "auction_id", "broker_id", "amount", "created_at")
            .order_by("-amount", "-created_at")
        )
