from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from curious_now.api.deps import get_db, require_admin
from curious_now.api.schemas import (
    AdminRunResponse,
    ContentType,
    ImportSourcePackResponse,
    ItemsFeedResponse,
    PatchFeedRequest,
    PatchSourceRequest,
    Source,
    SourceFeedHealth,
    SourcePack,
    SourceType,
    SourcesResponse,
)
from curious_now.db import DB
from curious_now.ingestion import ingest_due_feeds
from curious_now.repo_stage1 import (
    import_source_pack,
    list_items_feed,
    list_sources,
    patch_feed,
    patch_source,
)
from curious_now.settings import get_settings

router = APIRouter()


@router.get("/items/feed", response_model=ItemsFeedResponse)
def get_items_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_id: UUID | None = None,
    source_type: SourceType | None = None,
    content_type: ContentType | None = None,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ItemsFeedResponse:
    return list_items_feed(
        conn,
        page=page,
        page_size=page_size,
        source_id=source_id,
        source_type=source_type.value if source_type else None,
        content_type=content_type.value if content_type else None,
    )


@router.get("/sources", response_model=SourcesResponse)
def get_sources(conn: psycopg.Connection[Any] = Depends(get_db)) -> SourcesResponse:
    return list_sources(conn)


@router.post(
    "/admin/source_pack/import",
    dependencies=[Depends(require_admin)],
    response_model=ImportSourcePackResponse,
)
def post_admin_source_pack_import(
    pack: SourcePack,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ImportSourcePackResponse:
    return import_source_pack(conn, pack)


@router.patch(
    "/admin/sources/{id}",
    dependencies=[Depends(require_admin)],
    response_model=Source,
)
def patch_admin_source(
    id: UUID,  # noqa: A002
    patch: PatchSourceRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Source:
    try:
        return patch_source(conn, source_id=id, patch=patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.patch(
    "/admin/feeds/{id}",
    dependencies=[Depends(require_admin)],
    response_model=SourceFeedHealth,
)
def patch_admin_feed(
    id: UUID,  # noqa: A002
    patch: PatchFeedRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SourceFeedHealth:
    try:
        return patch_feed(conn, feed_id=id, patch=patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/ingestion/run",
    dependencies=[Depends(require_admin)],
    response_model=AdminRunResponse,
    status_code=202,
)
def post_admin_ingestion_run(
    background_tasks: BackgroundTasks,
    feed_id: UUID | None = None,
) -> AdminRunResponse:
    settings = get_settings()

    def _run() -> None:
        db = DB(settings.database_url)
        with db.connect(autocommit=True) as conn:
            ingest_due_feeds(conn, feed_id=feed_id, force=True)

    background_tasks.add_task(_run)
    return AdminRunResponse(status="accepted")
