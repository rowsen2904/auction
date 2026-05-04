from __future__ import annotations

from decimal import Decimal, InvalidOperation

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Auction, Bid
from .participants import add_participant_with_flag, list_participants
from .realtime import AUCTIONS_GLOBAL_GROUP, sealed_bids_group_name
from .serializers import BidSerializer
from .services.rules import (
    ctx_for,
    ensure_active_window,
    ensure_broker_verified,
    ensure_min_price,
    ensure_mode,
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
        .only("id", "auction_id", "broker_id", "amount", "created_at", "updated_at")
        .order_by("-created_at")[:limit]
    )
    return BidSerializer(qs, many=True).data


@database_sync_to_async
def _participants_snapshot(auction_id: int) -> list[int]:
    return list_participants(auction_id=auction_id)


def _place_open_bid_atomic_sync(
    *,
    auction_id: int,
    user,
    requested_amount: Decimal,
) -> tuple[dict, dict, dict | None, bool]:
    """
    Place or update a broker's single open bid.

    Returns (auction_patch, bid_data, participant_event | None, is_new_bid).
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

        ensure_broker_verified(user)
        ensure_mode(
            ctx,
            allowed={Auction.Mode.OPEN},
            message="Торги по протоколу WebSocket разрешены только на открытых аукционах.",
        )
        ensure_active_window(ctx)
        ensure_not_owner(ctx)

        amount = open_compute_amount(auction=auction, requested=requested_amount)
        ensure_min_price(ctx, amount=amount)

        existing_bid = (
            Bid.objects.filter(
                auction_id=auction.id,
                broker=user,
                is_sealed=False,
            )
            .select_for_update()
            .first()
        )

        if existing_bid:
            existing_bid.amount = amount
            existing_bid.save(update_fields=["amount", "updated_at"])
            bid = existing_bid
            is_new_bid = False
        else:
            bid = Bid.objects.create(
                auction_id=auction.id,
                broker=user,
                amount=amount,
                is_sealed=False,
            )
            is_new_bid = True

        # bids_count = number of unique participants (distinct bids)
        auction.bids_count = Bid.objects.filter(
            auction_id=auction.id, is_sealed=False
        ).count()
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

        cnt, is_new_participant = add_participant_with_flag(
            auction_id=auction.id,
            user_id=user.id,
            end_date=auction.end_date,
        )

        participant_event = None
        if is_new_participant:
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

        return auction_patch, BidSerializer(bid).data, participant_event, is_new_bid


_place_open_bid_atomic = database_sync_to_async(_place_open_bid_atomic_sync)


@database_sync_to_async
def _closed_bids_snapshot_for_user(
    user, auction_id: int
) -> tuple[dict, list[dict], list[int]]:
    auction = get_object_or_404(
        Auction.objects.only(
            "id",
            "mode",
            "owner_id",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "updated_at",
        ),
        pk=auction_id,
    )

    if auction.mode != Auction.Mode.CLOSED:
        raise ValidationError({"detail": "Только для закрытых аукционов."})

    if getattr(user, "is_broker", False):
        raise PermissionDenied(
            "Брокеру запрещён доступ к данным закрытых заявок " "через WebSocket."
        )

    is_admin = bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    )

    if not (is_admin or user.id == auction.owner_id):
        raise PermissionDenied(
            "Только владелец/администратор может просматривать список ставок."
        )

    qs = (
        Bid.objects.filter(auction_id=auction.id, is_sealed=True)
        .select_related("broker")
        .only("id", "auction_id", "broker_id", "amount", "created_at", "updated_at")
        .order_by("-amount", "-created_at")
    )

    participants = list_participants(auction_id=auction.id)

    auction_payload = {
        "id": auction.id,
        "bids_count": auction.bids_count,
        "current_price": str(auction.current_price),
        "highest_bid_id": auction.highest_bid_id,
        "updated_at": auction.updated_at.isoformat(),
    }

    return auction_payload, BidSerializer(qs, many=True).data, participants


class AuctionLiveBidConsumer(AsyncJsonWebsocketConsumer):
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
            await self.send_json(
                {"type": "error", "detail": "Неизвестный тип сообщения."}
            )
            return

        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.send_json(
                {"type": "error", "detail": "Требуется аутентификация."}
            )
            return
        if not getattr(user, "is_broker", False):
            await self.send_json(
                {"type": "error", "detail": "Только брокер может делать ставки."}
            )
            return

        raw_amount = content.get("amount")
        try:
            requested_amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError):
            await self.send_json({"type": "error", "detail": "Неверная сумма."})
            return

        try:
            auction_patch, bid_data, participant_event, is_new_bid = (
                await _place_open_bid_atomic(
                    auction_id=self.auction_id,
                    user=user,
                    requested_amount=requested_amount,
                )
            )
        except ValidationError as e:
            await self.send_json({"type": "error", "detail": e.detail})
            return
        except Exception:
            await self.send_json({"type": "error", "detail": "Внутренняя ошибка."})
            return

        if participant_event:
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "participant_joined", "payload": participant_event},
            )

        event_type = "bid_created" if is_new_bid else "bid_updated"
        await self.channel_layer.group_send(
            self.group_name,
            {"type": event_type, "auction": auction_patch, "bid": bid_data},
        )

    async def bid_created(self, event):
        await self.send_json(
            {"type": "bid_created", "auction": event["auction"], "bid": event["bid"]}
        )

    async def bid_updated(self, event):
        await self.send_json(
            {"type": "bid_updated", "auction": event["auction"], "bid": event["bid"]}
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


class ClosedAuctionBidsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.auction_id = int(self.scope["url_route"]["kwargs"]["auction_id"])
        self.group_name = sealed_bids_group_name(self.auction_id)

        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        if getattr(user, "is_broker", False):
            await self.close(code=4403)
            return

        try:
            auction_payload, bids, participants = await _closed_bids_snapshot_for_user(
                user, self.auction_id
            )
        except PermissionDenied:
            await self.close(code=4403)
            return
        except ValidationError:
            await self.close(code=4404)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_json(
            {
                "type": "sealed_bids_snapshot",
                "auction": auction_payload,
                "bids": bids,
                "participants": participants,
                "participants_count": len(participants),
            }
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        await self.send_json(
            {
                "type": "error",
                "detail": "Этот WebSocket только для чтения. "
                "Создание и изменение ставок выполняется через HTTP.",
            }
        )

    async def sealed_bid_changed(self, event):
        await self.send_json(
            {
                "type": "sealed_bid_changed",
                **event["payload"],
            }
        )

    async def sealed_participants_changed(self, event):
        await self.send_json(
            {
                "type": "sealed_participants_changed",
                **event["payload"],
            }
        )

    async def auction_updated(self, event):
        await self.send_json({"type": "auction_updated", **event["payload"]})


class AuctionsGlobalConsumer(AsyncJsonWebsocketConsumer):
    """
    Read-only firehose for auction status changes across the platform.
    Catalog/list pages subscribe to receive `auction_status_changed`
    events for any auction without having to know its id ahead of time.
    """

    async def connect(self):
        await self.channel_layer.group_add(AUCTIONS_GLOBAL_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(
            AUCTIONS_GLOBAL_GROUP, self.channel_name
        )

    async def receive_json(self, content, **kwargs):
        # Read-only channel.
        await self.send_json(
            {"type": "error", "detail": "Read-only channel."}
        )

    async def auction_status_changed(self, event):
        await self.send_json(
            {"type": "auction_status_changed", **event["payload"]}
        )
