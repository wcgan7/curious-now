from __future__ import annotations

import hashlib
import secrets
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from fastapi import Cookie, Depends, Header, HTTPException

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


@dataclass(frozen=True)
class AuthedUser:
    user_id: UUID
    email: str


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, _sha256_hex(token)


def require_user(
    conn: psycopg.Connection[Any] = Depends(get_db),
    cn_session: str | None = Cookie(default=None, alias="cn_session"),
) -> AuthedUser:
    if not cn_session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token_hash = _sha256_hex(cn_session)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, coalesce(u.email_raw, u.email_normalized) AS email
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token_hash = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > now();
            """,
            (token_hash,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return AuthedUser(user_id=row["user_id"], email=row["email"])


def optional_user(
    conn: psycopg.Connection[Any] = Depends(get_db),
    cn_session: str | None = Cookie(default=None, alias="cn_session"),
) -> AuthedUser | None:
    if not cn_session:
        return None
    token_hash = _sha256_hex(cn_session)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, coalesce(u.email_raw, u.email_normalized) AS email
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token_hash = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > now();
            """,
            (token_hash,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return AuthedUser(user_id=row["user_id"], email=row["email"])
