from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from psycopg.types.json import Jsonb

from curious_now.api.deps import AuthedUser, get_db, optional_user, require_user
from curious_now.api.schemas import (
    EventIn,
    EventsIngestResponse,
    MagicLinkStartRequest,
    MagicLinkStartResponse,
    MagicLinkVerifyRequest,
    MagicLinkVerifyResponse,
    SimpleOkResponse,
    UserPrefsPatchRequest,
    UserPrefsResponse,
    UserResponse,
    UserSavesResponse,
)
from curious_now.rate_limit import enforce_rate_limit
from curious_now.repo_stage5 import (
    block_source,
    create_magic_link_token,
    follow_topic,
    get_current_user,
    get_user_prefs,
    hide_cluster,
    list_saved_clusters,
    normalize_email,
    patch_user_prefs,
    revoke_session,
    save_cluster,
    simple_ok,
    unblock_source,
    unfollow_topic,
    unhide_cluster,
    unsave_cluster,
    verify_magic_link_token,
)
from curious_now.settings import get_settings

router = APIRouter()


@router.post("/auth/magic_link/start", response_model=MagicLinkStartResponse)
def post_magic_link_start(
    req: MagicLinkStartRequest,
    request: Request,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> MagicLinkStartResponse:
    enforce_rate_limit(request, key="auth_magic_link_start", limit=10, window_seconds=60)
    email_norm = normalize_email(req.email)
    if "@" not in email_norm:
        raise HTTPException(status_code=400, detail="Invalid email")
    _user_id, token = create_magic_link_token(conn, email=req.email)

    # v0/dev: we don't send email here; token is logged so a developer can complete the flow.
    if get_settings().log_magic_link_tokens:
        print(f"[magic_link] token for {email_norm}: {token}")
    return MagicLinkStartResponse(status="sent")


@router.post("/auth/magic_link/verify", response_model=MagicLinkVerifyResponse)
def post_magic_link_verify(
    req: MagicLinkVerifyRequest,
    response: Response,
    request: Request,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> MagicLinkVerifyResponse:
    enforce_rate_limit(request, key="auth_magic_link_verify", limit=20, window_seconds=60)
    try:
        user, session_token = verify_magic_link_token(conn, token=req.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired token") from None

    response.set_cookie(
        key="cn_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return MagicLinkVerifyResponse(user=user)


@router.post("/auth/logout", response_model=SimpleOkResponse)
def post_logout(
    response: Response,
    user: AuthedUser = Depends(require_user),
    cn_session: str | None = Cookie(default=None, alias="cn_session"),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    if not cn_session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    revoke_session(conn, session_token=cn_session)
    response.delete_cookie("cn_session", path="/")
    return SimpleOkResponse(status="ok")


@router.get("/user", response_model=UserResponse)
def get_user(
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> UserResponse:
    return get_current_user(conn, user_id=user.user_id)


@router.get("/user/prefs", response_model=UserPrefsResponse)
def get_user_prefs_route(
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> UserPrefsResponse:
    return get_user_prefs(conn, user_id=user.user_id)


@router.patch("/user/prefs", response_model=UserPrefsResponse)
def patch_user_prefs_route(
    patch: UserPrefsPatchRequest,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> UserPrefsResponse:
    return patch_user_prefs(
        conn,
        user_id=user.user_id,
        reading_mode_default=patch.reading_mode_default,
        notification_settings=patch.notification_settings,
    )


@router.post("/user/follows/topics/{topic_id}", response_model=SimpleOkResponse)
def post_follow_topic(
    topic_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    follow_topic(conn, user_id=user.user_id, topic_id=topic_id)
    return simple_ok()


@router.delete("/user/follows/topics/{topic_id}", response_model=SimpleOkResponse)
def delete_follow_topic(
    topic_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    unfollow_topic(conn, user_id=user.user_id, topic_id=topic_id)
    return simple_ok()


@router.post("/user/blocks/sources/{source_id}", response_model=SimpleOkResponse)
def post_block_source(
    source_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    block_source(conn, user_id=user.user_id, source_id=source_id)
    return simple_ok()


@router.delete("/user/blocks/sources/{source_id}", response_model=SimpleOkResponse)
def delete_block_source(
    source_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    unblock_source(conn, user_id=user.user_id, source_id=source_id)
    return simple_ok()


@router.post("/user/saves/{cluster_id}", response_model=SimpleOkResponse)
def post_save_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    save_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.delete("/user/saves/{cluster_id}", response_model=SimpleOkResponse)
def delete_save_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    unsave_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.post("/user/hides/{cluster_id}", response_model=SimpleOkResponse)
def post_hide_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    hide_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.delete("/user/hides/{cluster_id}", response_model=SimpleOkResponse)
def delete_hide_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    unhide_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.get("/user/saves", response_model=UserSavesResponse)
def get_user_saves(
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> UserSavesResponse:
    return list_saved_clusters(conn, user_id=user.user_id)


@router.post("/events", response_model=EventsIngestResponse, status_code=202)
def post_events(
    event: EventIn,
    user: AuthedUser | None = Depends(optional_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> EventsIngestResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO engagement_events(
              user_id, client_id, event_type, cluster_id, item_id, topic_id, meta
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                user.user_id if user else None,
                event.client_id,
                event.event_type,
                event.cluster_id,
                event.item_id,
                event.topic_id,
                Jsonb(event.meta or {}),
            ),
        )
    return EventsIngestResponse(status="accepted")
