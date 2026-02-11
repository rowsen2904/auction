from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Tuple

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django_redis import get_redis_connection


def _participants_key(auction_id: int) -> str:
    return f"auction:{auction_id}:participants"


def _broadcast_joined(
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


def _cache_timeout_seconds(end_date) -> int:
    expire_at = end_date + timedelta(days=1)
    seconds = int(
        (expire_at - expire_at.__class__.now(expire_at.tzinfo)).total_seconds()
    )
    return max(seconds, 60)


def add_participant_with_flag(
    *, auction_id: int, user_id: int, end_date
) -> Tuple[int, bool]:
    """
    Adds participant to Redis set.
    Fallback to Django cache if Redis backend is unavailable (tests/dev without Redis).
    Returns: (participants_count, was_added)
    """
    key = _participants_key(auction_id)

    try:
        r = get_redis_connection("default")
        added = int(r.sadd(key, str(user_id)))  # 1 if added, 0 if already present
        expire_at = end_date + timedelta(days=1)
        r.expireat(key, int(expire_at.timestamp()))
        count = int(r.scard(key))
        was_added = bool(added)
    except NotImplementedError:
        # Cache fallback (LocMem in tests)
        s = cache.get(key) or set()
        before = len(s)
        s.add(int(user_id))
        cache.set(key, s, timeout=_cache_timeout_seconds(end_date))
        count = len(s)
        was_added = len(s) > before

    if was_added:
        _broadcast_joined(
            auction_id=auction_id, user_id=user_id, participants_count=count
        )

    return count, was_added


def add_participant(*, auction_id: int, user_id: int, end_date) -> int:
    count, _ = add_participant_with_flag(
        auction_id=auction_id, user_id=user_id, end_date=end_date
    )
    return count


def is_participant(*, auction_id: int, user_id: int) -> bool:
    key = _participants_key(auction_id)
    try:
        r = get_redis_connection("default")
        return bool(r.sismember(key, str(user_id)))
    except NotImplementedError:
        s = cache.get(key) or set()
        return int(user_id) in s


def list_participants(*, auction_id: int) -> list[int]:
    key = _participants_key(auction_id)

    try:
        r = get_redis_connection("default")
        raw: Iterable[bytes] = r.smembers(key)
        out: list[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return sorted(out)
    except NotImplementedError:
        s = cache.get(key) or set()
        return sorted([int(x) for x in s])


def participants_count(*, auction_id: int) -> int:
    key = _participants_key(auction_id)
    try:
        r = get_redis_connection("default")
        return int(r.scard(key))
    except NotImplementedError:
        s = cache.get(key) or set()
        return len(s)


def remove_participant(*, auction_id: int, user_id: int) -> int:
    key = _participants_key(auction_id)
    try:
        r = get_redis_connection("default")
        r.srem(key, str(user_id))
        return int(r.scard(key))
    except NotImplementedError:
        s = cache.get(key) or set()
        s.discard(int(user_id))
        cache.set(key, s, timeout=3600)
        return len(s)
