from __future__ import annotations

import time
from ipaddress import ip_address
from typing import Any

from fastapi import HTTPException, Request
from redis import exceptions as redis_exceptions

from curious_now.cache import get_redis_client
from curious_now.settings import get_settings


def _client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                try:
                    ip_address(first)
                except ValueError:
                    pass
                else:
                    return first
        xri = request.headers.get("x-real-ip")
        if xri:
            ip = xri.strip()
            if ip:
                try:
                    ip_address(ip)
                except ValueError:
                    pass
                else:
                    return ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    r = get_redis_client()
    if r is None:
        return

    ip = _client_ip(request)
    window = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{ip}:{window}"

    try:
        pipe: Any = r.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 5)
        count = pipe.execute()[0]
    except redis_exceptions.RedisError:
        return

    try:
        c = int(count)
    except (TypeError, ValueError):
        return
    if c > limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


def enforce_user_rate_limit(
    request: Request,
    *,
    user_id: str | None,
    key: str,
    limit: int,
    window_seconds: int,
    fallback_to_ip: bool = True,
) -> None:
    """
    Enforce rate limiting by user ID (or IP as fallback).

    This provides per-user rate limiting for authenticated users,
    with optional fallback to IP-based limiting for anonymous requests.

    Args:
        request: The FastAPI request
        user_id: The authenticated user's ID (or None for anonymous)
        key: Rate limit key/bucket name
        limit: Maximum number of requests in the window
        window_seconds: The time window in seconds
        fallback_to_ip: Whether to fall back to IP limiting for anonymous users
    """
    r = get_redis_client()
    if r is None:
        return

    # Use user ID if authenticated, otherwise IP
    if user_id:
        identifier = f"user:{user_id}"
    elif fallback_to_ip:
        identifier = f"ip:{_client_ip(request)}"
    else:
        # Skip rate limiting for anonymous if no fallback
        return

    window = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{identifier}:{window}"

    try:
        pipe: Any = r.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 5)
        count = pipe.execute()[0]
    except redis_exceptions.RedisError:
        return

    try:
        c = int(count)
    except (TypeError, ValueError):
        return

    if c > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(window_seconds),
            },
        )


def get_rate_limit_status(
    request: Request,
    *,
    user_id: str | None,
    key: str,
    limit: int,
    window_seconds: int,
) -> dict[str, Any]:
    """
    Get the current rate limit status without enforcing it.

    Returns a dictionary with current count, limit, and remaining allowance.
    """
    r = get_redis_client()
    if r is None:
        return {
            "limit": limit,
            "remaining": limit,
            "reset_at": int(time.time()) + window_seconds,
            "redis_available": False,
        }

    # Use user ID if authenticated, otherwise IP
    if user_id:
        identifier = f"user:{user_id}"
    else:
        identifier = f"ip:{_client_ip(request)}"

    window = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{identifier}:{window}"

    try:
        count = r.get(redis_key)
        current = int(count) if count else 0  # type: ignore[arg-type]
    except (redis_exceptions.RedisError, TypeError, ValueError):
        current = 0

    return {
        "limit": limit,
        "remaining": max(0, limit - current),
        "reset_at": (window + 1) * window_seconds,
        "redis_available": True,
    }
