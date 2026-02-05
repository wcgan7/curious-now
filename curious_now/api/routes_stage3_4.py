from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from curious_now.api.deps import get_db
from curious_now.api.schemas import (
    ClusterUpdatesResponse,
    GlossaryLookupResponse,
    TopicLineageResponse,
)
from curious_now.repo_stage3 import glossary_lookup
from curious_now.repo_stage4 import get_cluster_updates, get_topic_lineage
from curious_now.repo_stage8 import topic_redirect_to

router = APIRouter()


@router.get("/glossary", response_model=GlossaryLookupResponse)
def get_glossary(
    term: str,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> GlossaryLookupResponse:
    try:
        return glossary_lookup(conn, term=term)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None


@router.get("/clusters/{id}/updates", response_model=ClusterUpdatesResponse)
def get_cluster_updates_route(
    id: UUID,  # noqa: A002
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ClusterUpdatesResponse:
    return get_cluster_updates(conn, cluster_id=id)


@router.get("/topics/{id}/lineage", response_model=TopicLineageResponse)
def get_topic_lineage_route(
    id: UUID,  # noqa: A002
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> TopicLineageResponse:
    to_id = topic_redirect_to(conn, topic_id=id)
    if to_id:
        return JSONResponse(  # type: ignore[return-value]
            status_code=301,
            content={"redirect_to_topic_id": str(to_id)},
        )
    return get_topic_lineage(conn, topic_id=id)
