from __future__ import annotations

from auctions.models import Auction, Bid
from auctions.schemas import closed_select_winner_schema, closed_shortlist_schema
from auctions.serializers import (
    ClosedSelectWinnerSerializer,
    ClosedShortlistSerializer,
)
from auctions.services.assignments import select_closed_auction_winner
from auctions.services.rules import is_admin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class ClosedShortlistView(APIView):
    permission_classes = [IsAuthenticated]

    @closed_shortlist_schema
    def post(self, request, pk: int):
        ser = ClosedShortlistSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        bid_ids = ser.validated_data["bid_ids"]

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().only(
                    "id",
                    "owner_id",
                    "mode",
                    "status",
                ),
                pk=pk,
            )

            if auction.mode != Auction.Mode.CLOSED:
                raise ValidationError({"detail": "Только для закрытых аукционов."})

            if auction.status != Auction.Status.FINISHED:
                raise ValidationError(
                    {
                        "detail": _(
                            "Составление списка финалистов допускается "
                            "только после завершения аукциона."
                        )
                    }
                )

            user = request.user
            if not (is_admin(user) or user.id == auction.owner_id):
                raise PermissionDenied(
                    "Только владелец/администратор может добавить в список кандидатов."
                )

            bids = list(
                Bid.objects.filter(
                    auction_id=auction.id,
                    id__in=bid_ids,
                    is_sealed=True,
                ).only("id")
            )

            if len(bids) != len(set(bid_ids)):
                raise ValidationError(
                    {
                        "detail": _(
                            "Некоторые bid_id не относятся к этому закрытому аукциону."
                        )
                    }
                )

            auction.shortlisted_bids.set([b.id for b in bids])

        return Response(
            {"shortlistedBidIds": [b.id for b in bids]},
            status=status.HTTP_200_OK,
        )


class ClosedSelectWinnerView(APIView):
    permission_classes = [IsAuthenticated]

    @closed_select_winner_schema
    def post(self, request, pk: int):
        ser = ClosedSelectWinnerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().prefetch_related(
                    "properties",
                    "shortlisted_bids",
                ),
                pk=pk,
            )

            if auction.mode != Auction.Mode.CLOSED:
                raise ValidationError({"detail": "Только для закрытых аукционов."})

            if auction.status != Auction.Status.FINISHED:
                raise ValidationError(
                    {
                        "detail": "Выбор победителей возможен только после завершения аукциона."
                    }
                )

            user = request.user
            if not (is_admin(user) or user.id == auction.owner_id):
                raise PermissionDenied(
                    "Победителей может выбрать только владелец/администратор."
                )

            bid = select_closed_auction_winner(
                auction=auction,
                broker_id=ser.validated_data["broker_id"],
            )

        return Response(
            {
                "auctionId": auction.id,
                "selectedBrokerId": bid.broker_id,
                "selectedBidId": bid.id,
            },
            status=status.HTTP_200_OK,
        )
