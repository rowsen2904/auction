from __future__ import annotations

from decimal import Decimal, InvalidOperation

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .models import Auction, Bid
from .participants import add_participant_with_flag, list_participants
from .serializers import BidSerializer
from .services.rules import (
    ctx_for,
    ensure_active_window,
    ensure_min_price,
    ensure_mode,
    ensure_not_current_leader,
    ensure_not_owner,
    open_compute_amount,
)


@database_sync_to_async
def _auction_snapshot(auction_id: int) -> dict:
    a = get_object_or_404(
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
        "id": a.id,
        "mode": a.mode,
        "status": a.status,
        "min_price": str(a.min_price),
        "start_date": a.start_date.isoformat(),
        "end_date": a.end_date.isoformat(),
        "bids_count": a.bids_count,
        "current_price": str(a.current_price),
        "highest_bid_id": a.highest_bid_id,
        "owner_id": a.owner_id,
        "updated_at": a.updated_at.isoformat(),
    }


@database_sync_to_async
def _last_bids(auction_id: int, limit: int = 50) -> list[dict]:
    qs = (
        Bid.objects.filter(auction_id=auction_id)
        .select_related("broker")
        .only("id", "auction_id", "broker_id", "amount", "created_at")
        .order_by("-created_at")[:limit]
    )
    return BidSerializer(qs, many=True).data


@database_sync_to_async
def _participants_snapshot(auction_id: int) -> list[int]:
    # Redis call in a thread
    return list_participants(auction_id=auction_id)


@database_sync_to_async
def _create_open_bid_atomic(
    *,
    auction_id: int,
    user,
    requested_amount: Decimal,
) -> tuple[dict, dict, dict | None]:
    """
    Creates OPEN bid with DB lock + updates cache.
    Auto-joins participant in Redis on successful bid creation.
    Returns:
      (auction_patch, bid_data, participant_event_or_none)
    """
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

        ctx = ctx_for(auction=auction, user=user)

        ensure_mode(
            ctx,
            allowed={Auction.Mode.OPEN},
            message="WebSocket bidding is allowed only for OPEN auctions.",
        )
        ensure_active_window(ctx)
        ensure_not_owner(ctx)
        ensure_not_current_leader(auction=auction, user_id=user.id)

        amount = open_compute_amount(auction=auction, requested=requested_amount)
        ensure_min_price(ctx, amount=amount)

        bid = Bid.objects.create(
            auction_id=auction.id,
            broker=user,
            amount=amount,
            is_sealed=False,
        )

        auction.bids_count += 1
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

        # Auto-join on bid (Redis)
        is_new, cnt = add_participant_with_flag(
            auction_id=auction.id,
            user_id=user.id,
            end_date=auction.end_date,
        )

        participant_event = None
        if is_new:
            participant_event = {
                "auction_id": auction.id,
                "user_id": user.id,
                "participants_count": cnt,
            }

        auction_patch = {
            "id": auction.id,
            "bids_count": auction.bids_count,
            "current_price": str(auction.current_price),
            "highest_bid_id": auction.highest_bid_id,
            "updated_at": auction.updated_at.isoformat(),
        }

        return auction_patch, BidSerializer(bid).data, participant_event


class AuctionLiveBidConsumer(AsyncJsonWebsocketConsumer):
    """
    WS: /ws/auctions/<auction_id>/

    Client:
      { "type": "bid", "amount": "2500000.00" }

    Server:
      { "type": "auction_snapshot", "auction": {...}, "bids": [...] }
      { "type": "participants_snapshot", "participants": [..] }
      { "type": "participant_joined", "auction_id": 1, "user_id": 10, "participants_count": 5 }
      { "type": "bid_created", "auction": {...}, "bid": {...} }
    """

    async def connect(self):
        self.auction_id = int(self.scope["url_route"]["kwargs"]["auction_id"])
        self.group_name = f"auction_{self.auction_id}"

        snapshot = await _auction_snapshot(self.auction_id)
        if snapshot["mode"] != Auction.Mode.OPEN:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        bids = await _last_bids(self.auction_id, limit=50)
        participants = await _participants_snapshot(self.auction_id)

        await self.send_json(
            {
                "type": "auction_snapshot",
                "auction": snapshot,
                "bids": bids,
            }
        )
        await self.send_json(
            {
                "type": "participants_snapshot",
                "participants": participants,
            }
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") != "bid":
            await self.send_json({"type": "error", "detail": "Unknown message type."})
            return

        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.send_json(
                {"type": "error", "detail": "Authentication required."}
            )
            return
        if not getattr(user, "is_broker", False):
            await self.send_json({"type": "error", "detail": "Only broker can bid."})
            return

        raw_amount = content.get("amount")
        try:
            requested_amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError):
            await self.send_json({"type": "error", "detail": "Invalid amount."})
            return

        try:
            auction_patch, bid_data, participant_event = await _create_open_bid_atomic(
                auction_id=self.auction_id,
                user=user,
                requested_amount=requested_amount,
            )
        except ValidationError as e:
            await self.send_json({"type": "error", "detail": e.detail})
            return
        except Exception:
            await self.send_json({"type": "error", "detail": "Internal error."})
            return

        # If participant is new -> notify everyone in realtime
        if participant_event:
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "participant_joined", "payload": participant_event},
            )

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "bid_created", "auction": auction_patch, "bid": bid_data},
        )

    async def bid_created(self, event):
        await self.send_json(
            {"type": "bid_created", "auction": event["auction"], "bid": event["bid"]}
        )

    async def auction_updated(self, event):
        await self.send_json({"type": "auction_updated", **event["payload"]})

    async def participant_joined(self, event):
        p = event["payload"]
        await self.send_json(
            {
                "type": "participant_joined",
                "auction_id": p["auction_id"],
                "user_id": p["user_id"],
                "participants_count": p["participants_count"],
            }
        )
