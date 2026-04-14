from __future__ import annotations

from decimal import Decimal

import auctions.participants as auction_participants
from asgiref.sync import async_to_sync
from auctions.models import Auction, Bid
from auctions.permissions import IsBroker
from auctions.realtime import broadcast_sealed_bid_changed, sealed_bids_group_name
from auctions.schemas import (
    closed_bid_create_schema,
    closed_bid_update_schema,
    sealed_bids_list_schema,
)
from auctions.serializers import BidCreateSerializer, BidSerializer, BidUpdateSerializer
from auctions.services.rules import (
    ctx_for,
    ensure_active_window,
    ensure_broker_verified,
    ensure_min_price,
    ensure_mode,
    ensure_not_owner,
    is_admin,
)
from channels.layers import get_channel_layer
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


def _broadcast_sealed_participants_changed(
    *,
    auction_id: int,
    action: str,
    user_id: int,
    participants: list[int],
) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        sealed_bids_group_name(auction_id),
        {
            "type": "sealed_participants_changed",
            "payload": {
                "action": action,
                "auction_id": auction_id,
                "user_id": user_id,
                "participants": participants,
                "participants_count": len(participants),
            },
        },
    )


def _recalc_closed_auction_state(*, auction: Auction) -> dict:
    qs = Bid.objects.filter(auction_id=auction.id, is_sealed=True)

    highest = qs.order_by("-amount", "-created_at").only("id", "amount").first()

    auction.bids_count = qs.count()
    auction.current_price = highest.amount if highest else Decimal("0.00")
    auction.highest_bid_id = highest.id if highest else None
    auction.save(
        update_fields=[
            "bids_count",
            "current_price",
            "highest_bid_id",
            "updated_at",
        ]
    )

    return {
        "id": auction.id,
        "bids_count": auction.bids_count,
        "current_price": str(auction.current_price),
        "highest_bid_id": auction.highest_bid_id,
        "updated_at": auction.updated_at.isoformat(),
    }


def _extract_was_added(participant_result) -> bool:
    if isinstance(participant_result, tuple) and len(participant_result) >= 2:
        return bool(participant_result[1])

    if isinstance(participant_result, list) and len(participant_result) >= 2:
        return bool(participant_result[1])

    if isinstance(participant_result, bool):
        return participant_result

    return False


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
                    "updated_at",
                ),
                pk=auction_id,
            )

            ctx = ctx_for(auction=auction, user=request.user)
            ensure_broker_verified(request.user)
            ensure_mode(
                ctx,
                allowed={Auction.Mode.CLOSED},
                message="Торги по протоколу HTTP разрешены только для закрытых аукционов.",
            )
            ensure_active_window(ctx)
            ensure_not_owner(ctx)
            ensure_min_price(ctx, amount=amount)

            if Bid.objects.filter(
                auction_id=auction.id,
                broker_id=request.user.id,
                is_sealed=True,
            ).exists():
                raise ValidationError(
                    {"detail": "В закрытом аукционе можно сделать только одну ставку."}
                )

            bid = Bid.objects.create(
                auction_id=auction.id,
                broker=request.user,
                amount=amount,
                is_sealed=True,
            )

            participant_result = auction_participants.add_participant_with_flag(
                auction_id=auction.id,
                user_id=request.user.id,
                end_date=auction.end_date,
            )
            was_added = _extract_was_added(participant_result)

            _recalc_closed_auction_state(auction=auction)
            bid_data = BidSerializer(bid).data
            participants = auction_participants.list_participants(auction_id=auction.id)

            def _after_commit():
                broadcast_sealed_bid_changed(
                    auction_id=auction.id,
                    action="created",
                    bid_payload=bid_data,
                )
                if was_added:
                    _broadcast_sealed_participants_changed(
                        auction_id=auction.id,
                        action="joined",
                        user_id=request.user.id,
                        participants=participants,
                    )

            transaction.on_commit(_after_commit)

        return Response(bid_data, status=status.HTTP_201_CREATED)


class MyClosedBidUpdateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsBroker]
    serializer_class = BidUpdateSerializer
    http_method_names = ["patch", "delete", "head", "options"]

    @closed_bid_update_schema
    def patch(self, request, *args, **kwargs):
        auction_id = int(kwargs["pk"])

        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data.get("amount")
        if amount is None:
            raise ValidationError({"amount": "Это поле обязательно к заполнению."})

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
                    "bids_count",
                    "updated_at",
                ),
                pk=auction_id,
            )

            ctx = ctx_for(auction=auction, user=request.user)
            ensure_broker_verified(request.user)
            ensure_mode(
                ctx,
                allowed={Auction.Mode.CLOSED},
                message=_(
                    "Обновление ставок по протоколу HTTP "
                    "разрешено только для закрытых аукционов."
                ),
            )
            ensure_active_window(ctx)
            ensure_not_owner(ctx)
            ensure_min_price(ctx, amount=amount)

            bid = get_object_or_404(
                Bid.objects.select_for_update().only(
                    "id",
                    "amount",
                    "auction_id",
                    "broker_id",
                    "is_sealed",
                    "created_at",
                ),
                auction_id=auction.id,
                broker_id=request.user.id,
                is_sealed=True,
            )

            bid.amount = amount
            bid.save(update_fields=["amount"])

            _recalc_closed_auction_state(auction=auction)
            bid_data = BidSerializer(bid).data

            transaction.on_commit(
                lambda: broadcast_sealed_bid_changed(
                    auction_id=auction.id,
                    action="updated",
                    bid_payload=bid_data,
                )
            )

        return Response(bid_data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        auction_id = int(kwargs["pk"])

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
                    "bids_count",
                    "updated_at",
                ),
                pk=auction_id,
            )

            ctx = ctx_for(auction=auction, user=request.user)
            ensure_broker_verified(request.user)
            ensure_mode(
                ctx,
                allowed={Auction.Mode.CLOSED},
                message=_(
                    "Удаление ставок по протоколу HTTP "
                    "разрешено только для закрытых аукционов."
                ),
            )
            ensure_active_window(ctx)
            ensure_not_owner(ctx)

            bid = get_object_or_404(
                Bid.objects.select_for_update().only(
                    "id",
                    "amount",
                    "auction_id",
                    "broker_id",
                    "is_sealed",
                    "created_at",
                ),
                auction_id=auction.id,
                broker_id=request.user.id,
                is_sealed=True,
            )

            deleted_bid_id = bid.id
            bid.delete()

            _recalc_closed_auction_state(auction=auction)

            auction_participants.participants_count(auction_id=auction.id)
            auction_participants.remove_participant(
                auction_id=auction.id,
                user_id=request.user.id,
            )
            participants = auction_participants.list_participants(auction_id=auction.id)

            def _after_commit():
                broadcast_sealed_bid_changed(
                    auction_id=auction.id,
                    action="deleted",
                    bid_payload={"id": deleted_bid_id},
                )
                _broadcast_sealed_participants_changed(
                    auction_id=auction.id,
                    action="left",
                    user_id=request.user.id,
                    participants=participants,
                )

            transaction.on_commit(_after_commit)

        return Response(status=status.HTTP_204_NO_CONTENT)


class ClosedBidsListForOwnerAdminView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BidSerializer

    @sealed_bids_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        auction_id = int(self.kwargs["pk"])
        auction = get_object_or_404(
            Auction.objects.only("id", "owner_id", "mode"),
            pk=auction_id,
        )

        if auction.mode != Auction.Mode.CLOSED:
            raise ValidationError({"detail": "Только для закрытых аукционов."})

        if not (
            is_admin(self.request.user) or self.request.user.id == auction.owner_id
        ):
            raise PermissionDenied(
                "Только владелец/администратор может просматривать запечатанные заявки."
            )

        return (
            Bid.objects.filter(auction_id=auction.id, is_sealed=True)
            .select_related("broker")
            .only("id", "auction_id", "broker_id", "amount", "created_at")
            .order_by("-amount", "-created_at")
        )
