from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from curious_now.api.deps import get_db
from curious_now.api.schemas import (
    ClusterDetail,
    ClustersFeedResponse,
    ContentType,
    RedirectResponse,
    SearchResponse,
    TopicDetail,
    TopicsResponse,
)
from curious_now.cache import (
    cache_get_json,
    cache_key_search,
    cache_set_json,
    get_redis_client,
    weak_etag,
)
from curious_now.rate_limit import enforce_rate_limit
from curious_now.repo_stage2 import (
    cluster_redirect_to,
    get_cluster_detail_or_redirect,
    get_cluster_updated_at,
    get_feed,
    get_topic_detail,
    get_topic_updated_at,
    list_topics,
    search,
)
from curious_now.repo_stage8 import topic_redirect_to

router = APIRouter()


@router.get("/feed", response_model=ClustersFeedResponse)
def get_clusters_feed(
    tab: Literal["latest", "trending"] = "latest",
    topic_id: UUID | None = None,
    content_type: ContentType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ClustersFeedResponse:
    r = get_redis_client()
    cache_key = (
        f"feed:{tab}:{topic_id or 'all'}:{content_type.value if content_type else 'all'}:"
        f"{page}:{page_size}"
    )
    if r:
        cached = cache_get_json(r, cache_key)
        if cached is not None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=200,
                content=cached,
                headers={"X-Cache": "hit"},
            )

    result = get_feed(
        conn,
        tab=tab,
        topic_id=topic_id,
        content_type=content_type.value if content_type else None,
        page=page,
        page_size=page_size,
    )

    if r:
        cache_set_json(r, cache_key, result.model_dump(mode="json"), ttl_seconds=60)
    return result


@router.get("/clusters/{id}", response_model=ClusterDetail)
def get_cluster(
    id: UUID,  # noqa: A002
    request: Request,
    response: Response,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ClusterDetail:
    to_id = cluster_redirect_to(conn, cluster_id=id)
    if to_id:
        return JSONResponse(  # type: ignore[return-value]
            status_code=301,
            content={"redirect_to_cluster_id": str(to_id)},
        )

    updated_at = get_cluster_updated_at(conn, cluster_id=id)
    if updated_at is None:
        raise HTTPException(status_code=404, detail="Not found")
    version = updated_at.isoformat()
    etag = weak_etag(f"cluster:{id}:{version}")
    response.headers["ETag"] = etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})  # type: ignore[return-value]

    r = get_redis_client()
    cache_key = f"cluster:{id}:v{version}"
    if r:
        cached = cache_get_json(r, cache_key)
        if cached is not None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=200,
                content=cached,
                headers={"ETag": etag, "X-Cache": "hit"},
            )
        response.headers["X-Cache"] = "miss"

    try:
        result = get_cluster_detail_or_redirect(conn, cluster_id=id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if isinstance(result, RedirectResponse):
        return JSONResponse(status_code=301, content=result.model_dump(mode="json"))  # type: ignore[return-value]

    if r:
        cache_set_json(r, cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
    return result


@router.get("/topics", response_model=TopicsResponse)
def get_topics(conn: psycopg.Connection[Any] = Depends(get_db)) -> TopicsResponse:
    return list_topics(conn)


@router.get("/topics/{id}", response_model=TopicDetail)
def get_topic(
    id: UUID,  # noqa: A002
    request: Request,
    response: Response,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> TopicDetail:
    to_id = topic_redirect_to(conn, topic_id=id)
    if to_id:
        return JSONResponse(  # type: ignore[return-value]
            status_code=301,
            content={"redirect_to_topic_id": str(to_id)},
        )

    updated_at = get_topic_updated_at(conn, topic_id=id)
    if updated_at is None:
        raise HTTPException(status_code=404, detail="Not found")
    version = updated_at.isoformat()
    etag = weak_etag(f"topic:{id}:{version}")
    response.headers["ETag"] = etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})  # type: ignore[return-value]

    r = get_redis_client()
    cache_key = f"topic:{id}:v{version}"
    if r:
        cached = cache_get_json(r, cache_key)
        if cached is not None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=200,
                content=cached,
                headers={"ETag": etag, "X-Cache": "hit"},
            )
        response.headers["X-Cache"] = "miss"

    try:
        result = get_topic_detail(conn, topic_id=id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if r:
        cache_set_json(r, cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
    return result


@router.get("/search", response_model=SearchResponse)
def get_search(
    request: Request,
    q: str = Query(..., min_length=1),  # noqa: A002
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SearchResponse:
    enforce_rate_limit(request, key="search_get", limit=120, window_seconds=60)
    r = get_redis_client()
    cache_key = cache_key_search(q)
    if r:
        cached = cache_get_json(r, cache_key)
        if cached is not None:
            return JSONResponse(  # type: ignore[return-value]
                status_code=200,
                content=cached,
                headers={"X-Cache": "hit"},
            )
    result = search(conn, query=q)
    if r:
        cache_set_json(r, cache_key, result.model_dump(mode="json"), ttl_seconds=60)
    return result
