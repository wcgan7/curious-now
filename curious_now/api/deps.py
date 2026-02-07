from __future__ import annotations

import secrets
from collections.abc import Generator
from typing import Any

import psycopg
from fastapi import Header, HTTPException

from curious_now.db import DB
from curious_now.settings import get_settings


def get_db() -> Generator[psycopg.Connection[Any], None, None]:
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect() as conn:
        yield conn


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(status_code=500, detail="Admin token not configured")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
