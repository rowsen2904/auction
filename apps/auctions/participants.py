from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django_redis import get_redis_connection


def _participants_key(auction_id: int) -> str:
    return f"auction:{auction_id}:participants"


def add_participant(*, auction_id: int, user_id: int, end_date) -> int:
    """
    Add user_id to auction participants set.
    Returns current participants count.
    """
    r = get_redis_connection("default")
    key = _participants_key(auction_id)

    # Redis set -> idempotent join (SADD won't duplicate)
    r.sadd(key, str(user_id))

    # Auto cleanup: expire after auction end + 1 day
    expire_at = end_date + timedelta(days=1)
    r.expireat(key, int(expire_at.timestamp()))

    return int(r.scard(key))


def is_participant(*, auction_id: int, user_id: int) -> bool:
    """Check if user_id is in auction participants."""
    r = get_redis_connection("default")
    key = _participants_key(auction_id)
    return bool(r.sismember(key, str(user_id)))


def list_participants(*, auction_id: int) -> list[int]:
    """Return participant user_ids (ints)."""
    r = get_redis_connection("default")
    key = _participants_key(auction_id)

    raw: Iterable[bytes] = r.smembers(key)
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def participants_count(*, auction_id: int) -> int:
    r = get_redis_connection("default")
    return int(r.scard(_participants_key(auction_id)))


def remove_participant(*, auction_id: int, user_id: int) -> int:
    """Optional: remove participant; returns new count."""
    r = get_redis_connection("default")
    key = _participants_key(auction_id)
    r.srem(key, str(user_id))
    return int(r.scard(key))
