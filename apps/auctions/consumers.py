from __future__ import annotations

from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Auction, Bid
from .serializers import BidSerializer


@sync_to_async
def _get_auction_snapshot(auction_id: int) -> dict:
    """
    Return minimal auction snapshot for initial payload.
    """
    auction = get_object_or_404(
        Auction.objects.only(
            "id",
            "mode",
            "status",
            "min_price",
            "start_date",
            "end_date",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "owner_id",
            "updated_at",
        ),
        pk=auction_id,
    )

    return {
        "id": auction.id,
        "mode": auction.mode,
        "status": auction.status,
        "min_price": str(auction.min_price),
        "start_date": auction.start_date.isoformat(),
        "end_date": auction.end_date.isoformat(),
        "bids_count": auction.bids_count,
        "current_price": str(auction.current_price),
        "highest_bid_id": auction.highest_bid_id,
        "owner_id": auction.owner_id,
        "updated_at": auction.updated_at.isoformat(),
    }


@sync_to_async
def _get_last_bids(auction_id: int, limit: int = 50) -> list[dict]:
    """
    Return last N bids for OPEN auction (public).
    """
    qs = (
        Bid.objects.filter(auction_id=auction_id)
        .select_related("broker")
        .order_by("-created_at")[:limit]
    )
    return BidSerializer(qs, many=True).data


@sync_to_async
def _create_bid_atomic(*, auction_id: int, user, amount: Decimal) -> tuple[dict, dict]:
    """
    Create a bid with race protection and update cached fields.
    Returns (auction_patch, bid_data).
    """
    now = timezone.now()

    with transaction.atomic():
        auction = get_object_or_404(
            Auction.objects.select_for_update().only(
                "id",
                "owner_id",
                "mode",
                "min_price",
                "start_date",
                "end_date",
                "status",
                "bids_count",
                "current_price",
                "highest_bid_id",
                "updated_at",
            ),
            pk=auction_id,
        )

        # Only OPEN auctions are supported via WebSocket
        if auction.mode != Auction.Mode.OPEN:
            raise ValidationError(
                {"detail": "WebSocket bidding is allowed only for OPEN auctions."}
            )

        if auction.status != Auction.Status.ACTIVE:
            raise ValidationError({"detail": "Auction is not active."})

        if not (auction.start_date <= now < auction.end_date):
            raise ValidationError(
                {"detail": "Auction is not within active time window."}
            )

        if user.id == auction.owner_id:
            raise ValidationError({"detail": "Owner cannot bid on their own auction."})

        if amount < auction.min_price:
            raise ValidationError({"detail": "Bid amount is below min_price."})

        # OPEN: must be strictly higher than current_price
        if amount <= auction.current_price:
            raise ValidationError({"detail": "Bid must be higher than current price."})

        bid = Bid.objects.create(
            auction_id=auction.id,
            broker=user,
            amount=amount,
        )

        auction.bids_count = auction.bids_count + 1
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

        auction_patch = {
            "id": auction.id,
            "bids_count": auction.bids_count,
            "current_price": str(auction.current_price),
            "highest_bid_id": auction.highest_bid_id,
            "updated_at": auction.updated_at.isoformat(),
        }

        bid_data = BidSerializer(bid).data

    return auction_patch, bid_data


class AuctionLiveBidConsumer(AsyncJsonWebsocketConsumer):
    """
    Live bids for OPEN auctions.
    Client messages:
      { "type": "bid", "amount": "2500.00" }

    Server broadcasts:
      { "type": "bid_created", "auction": {...}, "bid": {...} }
    """

    async def connect(self):
        self.auction_id = int(self.scope["url_route"]["kwargs"]["auction_id"])
        self.group_name = f"auction_{self.auction_id}"

        # Allow anyone to WATCH open auction, but only brokers can place bids.
        snapshot = await _get_auction_snapshot(self.auction_id)

        # If auction is not OPEN, block WS completely (you said closed will be HTTP)
        if snapshot["mode"] != Auction.Mode.OPEN:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send initial state
        bids = await _get_last_bids(self.auction_id, limit=50)
        await self.send_json(
            {
                "type": "auction_snapshot",
                "auction": snapshot,
                "bids": bids,
            }
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")

        if msg_type != "bid":
            await self.send_json({"type": "error", "detail": "Unknown message type."})
            return

        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.send_json(
                {"type": "error", "detail": "Authentication required."}
            )
            return

        # Your IsBroker permission uses user.is_broker
        if not getattr(user, "is_broker", False):
            await self.send_json({"type": "error", "detail": "Only broker can bid."})
            return

        raw_amount = content.get("amount")
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError):
            await self.send_json({"type": "error", "detail": "Invalid amount."})
            return

        try:
            auction_patch, bid_data = await _create_bid_atomic(
                auction_id=self.auction_id,
                user=user,
                amount=amount,
            )
        except ValidationError as e:
            # DRF ValidationError -> return readable error
            detail = e.detail if hasattr(e, "detail") else {"detail": str(e)}
            await self.send_json({"type": "error", "detail": detail})
            return
        except Exception:
            await self.send_json({"type": "error", "detail": "Internal error."})
            return

        # Broadcast to everyone watching this auction
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "bid_created",
                "auction": auction_patch,
                "bid": bid_data,
            },
        )

    async def bid_created(self, event):
        await self.send_json(
            {
                "type": "bid_created",
                "auction": event["auction"],
                "bid": event["bid"],
            }
        )

    async def auction_updated(self, event):
        await self.send_json({"type": "auction_updated", **event["payload"]})
