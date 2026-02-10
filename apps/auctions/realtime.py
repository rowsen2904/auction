from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_auction_status(*, auction_id: int, payload: dict) -> None:
    """
    Send auction updates to WS group.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"auction_{auction_id}",
        {"type": "auction_updated", "payload": payload},
    )
