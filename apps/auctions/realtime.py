from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_auction_status(*, auction_id: int, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f"auction_{auction_id}",
        {"type": "auction_updated", "payload": payload},
    )


def broadcast_participant_joined(
    *, auction_id: int, user_id: int, participants_count: int
) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f"auction_{auction_id}",
        {
            "type": "participant_joined",
            "payload": {
                "auction_id": auction_id,
                "user_id": user_id,
                "participants_count": participants_count,
            },
        },
    )
