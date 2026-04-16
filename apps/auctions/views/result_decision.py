from __future__ import annotations

from auctions.models import Auction
from auctions.schemas import (
    auction_confirm_result_schema,
    auction_reject_result_schema,
)
from auctions.services.result_decision import (
    confirm_auction_result,
    reject_auction_result,
)
from auctions.services.rules import is_admin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class _RejectResultSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=2000)


def _get_auction_for_owner_decision(pk: int, user) -> Auction:
    auction = get_object_or_404(
        Auction.objects.select_for_update()
        .select_related("owner", "real_property")
        .prefetch_related("properties"),
        pk=pk,
    )
    if not (is_admin(user) or user.id == auction.owner_id):
        raise PermissionDenied(
            _(
                "Решение по результату аукциона доступно только владельцу или администратору."
            )
        )
    return auction


class AuctionConfirmResultView(APIView):
    permission_classes = [IsAuthenticated]

    @auction_confirm_result_schema
    def post(self, request, pk: int):
        with transaction.atomic():
            auction = _get_auction_for_owner_decision(pk, request.user)
            deals = confirm_auction_result(auction=auction)

        return Response(
            {
                "auctionId": auction.id,
                "ownerDecision": auction.owner_decision,
                "createdDealIds": [d.id for d in deals],
            },
            status=status.HTTP_200_OK,
        )


class AuctionRejectResultView(APIView):
    permission_classes = [IsAuthenticated]

    @auction_reject_result_schema
    def post(self, request, pk: int):
        ser = _RejectResultSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data["reason"]

        with transaction.atomic():
            auction = _get_auction_for_owner_decision(pk, request.user)
            reject_auction_result(auction=auction, reason=reason)

        return Response(
            {
                "auctionId": auction.id,
                "status": auction.status,
                "ownerDecision": auction.owner_decision,
            },
            status=status.HTTP_200_OK,
        )
