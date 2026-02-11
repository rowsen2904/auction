from __future__ import annotations

from auctions.models import Auction
from auctions.permissions import IsAuctionOwnerOrAdmin
from auctions.schemas import auction_cancel_schema
from auctions.services.rules import ensure_can_cancel
from auctions.tasks import cancel_auction_status_tasks
from django.db import transaction
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class AuctionCancelView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsAuctionOwnerOrAdmin]
    http_method_names = ["delete", "head", "options"]

    def get_queryset(self):
        return Auction.objects.exclude(
            Q(status=Auction.Status.CANCELLED) | Q(status=Auction.Status.FINISHED)
        )

    def perform_destroy(self, instance: Auction) -> None:
        with transaction.atomic():
            auction = Auction.objects.select_for_update().get(pk=instance.pk)

            ensure_can_cancel(auction=auction, user=self.request.user)

            auction.status = Auction.Status.CANCELLED
            auction.save(update_fields=["status", "updated_at"])

            transaction.on_commit(
                lambda: cancel_auction_status_tasks(auction_id=auction.id)
            )

    @auction_cancel_schema
    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)
