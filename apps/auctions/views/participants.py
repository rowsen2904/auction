from __future__ import annotations

from auctions.models import Auction
from auctions.participants import add_participant, list_participants
from auctions.permissions import IsBroker
from auctions.realtime import broadcast_participant_joined
from auctions.schemas import join_schema, participants_list_schema
from auctions.services.rules import is_admin
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class AuctionJoinView(APIView):
    permission_classes = [IsAuthenticated, IsBroker]

    @join_schema
    def post(self, request, pk: int):
        auction = get_object_or_404(
            Auction.objects.only("id", "owner_id", "end_date", "status"), pk=pk
        )

        if request.user.id == auction.owner_id:
            raise ValidationError(
                {"detail": "Владелец не может присоединиться в качестве участника."}
            )

        if auction.status in (Auction.Status.CANCELLED, Auction.Status.FINISHED):
            raise ValidationError({"detail": "К аукциону нельзя присоединиться."})

        count = add_participant(
            auction_id=auction.id, user_id=request.user.id, end_date=auction.end_date
        )
        broadcast_participant_joined(
            auction_id=auction.id, user_id=request.user.id, participants_count=count
        )

        return Response(
            {
                "auction_id": auction.id,
                "user_id": request.user.id,
                "participants_count": count,
            },
            status=status.HTTP_200_OK,
        )


class AuctionParticipantsView(APIView):
    permission_classes = [IsAuthenticated]

    @participants_list_schema
    def get(self, request, pk: int):
        auction = get_object_or_404(
            Auction.objects.only("id", "mode", "owner_id"), pk=pk
        )

        # CLOSED: only owner/admin
        if auction.mode == Auction.Mode.CLOSED and not (
            is_admin(request.user) or request.user.id == auction.owner_id
        ):
            raise PermissionDenied(
                (
                    "Только владелец/администратор может просматривать "
                    "список участников завершившихся аукций."
                )
            )

        participants = list_participants(auction_id=auction.id)
        return Response(
            {"auction_id": auction.id, "participants": participants},
            status=status.HTTP_200_OK,
        )
