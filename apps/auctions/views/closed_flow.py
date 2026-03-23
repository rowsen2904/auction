from __future__ import annotations

from auctions.models import Auction, Bid
from auctions.schemas import closed_select_winner_schema, closed_shortlist_schema
from auctions.serializers import ClosedSelectWinnerSerializer, ClosedShortlistSerializer
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
                    "id", "owner_id", "mode", "status"
                ),
                pk=pk,
            )

            if auction.mode != Auction.Mode.CLOSED:
                raise ValidationError({"detail": "Только для закрытых аукционов."})
            if auction.status != Auction.Status.FINISHED:
                raise ValidationError(
                    {
                        "detail": _(
                            "Составление предварительного списка кандидатов "
                            "допускается только после завершения аукциона."
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
                    auction_id=auction.id, id__in=bid_ids, is_sealed=True
                ).only("id")
            )
            if len(bids) != len(set(bid_ids)):
                raise ValidationError(
                    {
                        "detail": _(
                            "Некоторые идентификаторы ставок (bid_id) "
                            "не относятся к этому аукциону."
                        )
                    }
                )

            auction.shortlisted_bids.set([b.id for b in bids])

        return Response({"shortlisted_bid_ids": bid_ids}, status=status.HTTP_200_OK)


class ClosedSelectWinnerView(APIView):
    permission_classes = [IsAuthenticated]

    @closed_select_winner_schema
    def post(self, request, pk: int):
        ser = ClosedSelectWinnerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        bid_id = ser.validated_data["bid_id"]

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().only(
                    "id", "owner_id", "mode", "status", "winner_bid_id"
                ),
                pk=pk,
            )

            if auction.mode != Auction.Mode.CLOSED:
                raise ValidationError({"detail": "Только для закрытых аукционов."})
            if auction.status != Auction.Status.FINISHED:
                raise ValidationError(
                    {
                        "detail": "Выбор победителя возможен только после завершения аукциона."
                    }
                )

            user = request.user
            if not (is_admin(user) or user.id == auction.owner_id):
                raise PermissionDenied(
                    "Победителя может выбрать только владелец/администратор."
                )

            bid = get_object_or_404(
                Bid.objects.only("id", "auction_id"),
                pk=bid_id,
                auction_id=auction.id,
                is_sealed=True,
            )

            if not auction.shortlisted_bids.filter(id=bid.id).exists():
                raise ValidationError(
                    {"detail": "Победитель должен быть выбран из списка финалистов."}
                )

            auction.winner_bid_id = bid.id
            auction.save(update_fields=["winner_bid_id", "updated_at"])

        return Response({"winner_bid_id": bid_id}, status=status.HTTP_200_OK)
