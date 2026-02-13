from __future__ import annotations

import secrets
from collections.abc import Generator
from typing import Any

import psycopg
from fastapi import Header, HTTPException, Request

from curious_now.db import DB
from curious_now.settings import get_settings


def _build_runtime_db() -> DB:
    settings = get_settings()
    return DB(
        settings.database_url,
        pool_enabled=False,
        pool_min_size=settings.db_pool_min_size,
        pool_max_size=settings.db_pool_max_size,
        pool_timeout_seconds=settings.db_pool_timeout_seconds,
    )


def get_db(request: Request) -> Generator[psycopg.Connection[Any], None, None]:
    runtime_db = getattr(request.app.state, "db", None)
    db = runtime_db if isinstance(runtime_db, DB) else _build_runtime_db()
    with db.connection() as conn:
        yield conn


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(status_code=500, detail="Admin token not configured")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
