from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import redis

from curious_now.settings import get_settings


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis | None:
    settings = get_settings()
    if not settings.redis_url:
        return None
    return redis.Redis.from_url(settings.redis_url)


def clear_redis_client_cache() -> None:
    get_redis_client.cache_clear()


def cache_get_json(r: redis.Redis, key: str) -> Any | None:
    try:
        raw = r.get(key)
    except redis.RedisError:
        return None
    if not raw:
        return None
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_set_json(r: redis.Redis, key: str, value: Any, *, ttl_seconds: int) -> None:
    try:
        raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        r.setex(key, ttl_seconds, raw)
    except (TypeError, redis.RedisError):
        return


def cache_key_search(query: str) -> str:
    return f"search:{_sha256_hex(query.strip().lower())}"


def weak_etag(value: str) -> str:
    return f'W/"{value}"'
