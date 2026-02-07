"""Stage 7: PWA + Performance + Caching routes.

This module provides endpoints for Progressive Web App functionality,
caching hints, and vector search.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from curious_now.api.deps import get_db, require_admin
from curious_now.api.schemas import SimpleOkResponse, simple_ok
from curious_now.cache import get_redis_client
from curious_now.settings import get_settings

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class ManifestResponse(BaseModel):
    """PWA Web App Manifest."""

    model_config = ConfigDict(from_attributes=True)

    name: str = "Curious Now"
    short_name: str = "Curious"
    description: str = "Science news that makes you think"
    start_url: str = "/"
    display: Literal["standalone", "fullscreen", "minimal-ui", "browser"] = "standalone"
    background_color: str = "#ffffff"
    theme_color: str = "#1a4d7c"
    orientation: Literal["portrait", "landscape", "any"] = "any"
    icons: list[dict[str, Any]] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=lambda: ["news", "science", "education"])


class VectorSearchRequest(BaseModel):
    """Request for semantic/vector search."""

    model_config = ConfigDict(from_attributes=True)

    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


class VectorSearchResult(BaseModel):
    """Single vector search result."""

    model_config = ConfigDict(from_attributes=True)

    cluster_id: UUID
    canonical_title: str
    takeaway: str | None = None
    similarity_score: float


class VectorSearchResponse(BaseModel):
    """Response from vector search."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    results: list[VectorSearchResult]
    fallback_to_fts: bool = False


class CacheStatsResponse(BaseModel):
    """Cache statistics for monitoring."""

    model_config = ConfigDict(from_attributes=True)

    redis_available: bool
    keys_count: int | None = None
    memory_used_bytes: int | None = None
    uptime_seconds: int | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/manifest.json", response_model=ManifestResponse)
def get_manifest() -> ManifestResponse:
    """
    Return PWA Web App Manifest.

    This endpoint provides the manifest.json required for PWA installation.
    """
    settings = get_settings()
    base_url = settings.public_app_base_url.rstrip("/")

    return ManifestResponse(
        name="Curious Now",
        short_name="Curious",
        description="Science news that makes you think",
        start_url="/",
        display="standalone",
        background_color="#ffffff",
        theme_color="#1a4d7c",
        orientation="any",
        icons=[
            {
                "src": f"{base_url}/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": f"{base_url}/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
            },
            {
                "src": f"{base_url}/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
        categories=["news", "science", "education"],
    )


@router.post("/search/semantic", response_model=VectorSearchResponse)
def semantic_search(
    request: VectorSearchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> VectorSearchResponse:
    """
    Perform semantic/vector search using pgvector.

    Falls back to full-text search if vector search is not available.
    """
    from curious_now.ai.embeddings import generate_query_embedding, get_embedding_provider

    # Check if pgvector is available
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            ) AS has_vector;
            """
        )
        row = cur.fetchone()
        has_vector = row["has_vector"] if row else False

    if not has_vector:
        return _fallback_fts_search(conn, request.query, request.limit)

    # Check if we have any embeddings in the cluster_embeddings table
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS(
                SELECT 1 FROM cluster_embeddings LIMIT 1
            ) AS has_embeddings;
            """
        )
        row = cur.fetchone()
        has_embeddings = row["has_embeddings"] if row else False

    if not has_embeddings:
        return _fallback_fts_search(conn, request.query, request.limit)

    # Generate query embedding
    try:
        provider = get_embedding_provider()
        query_result = generate_query_embedding(request.query, provider=provider)

        if not query_result.success or not query_result.embedding:
            return _fallback_fts_search(conn, request.query, request.limit)

        query_embedding = query_result.embedding
    except Exception:
        return _fallback_fts_search(conn, request.query, request.limit)

    # Perform vector similarity search using pgvector
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                1 - (ce.embedding <=> %s::vector) AS similarity_score
            FROM cluster_embeddings ce
            JOIN story_clusters c ON c.id = ce.cluster_id
            WHERE c.status = 'active'
            ORDER BY ce.embedding <=> %s::vector
            LIMIT %s;
            """,
            (query_embedding, query_embedding, request.limit),
        )
        rows = cur.fetchall()

    results = []
    for r in rows:
        results.append(
            VectorSearchResult(
                cluster_id=r["cluster_id"],
                canonical_title=r["canonical_title"],
                takeaway=r["takeaway"],
                similarity_score=float(r["similarity_score"]) if r["similarity_score"] else 0.0,
            )
        )

    return VectorSearchResponse(
        query=request.query,
        results=results,
        fallback_to_fts=False,
    )


def _fallback_fts_search(
    conn: psycopg.Connection[Any], query: str, limit: int
) -> VectorSearchResponse:
    """Fall back to full-text search when vector search is unavailable."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                ts_rank(sd.search_tsv, plainto_tsquery('english', %s)) AS score
            FROM story_clusters c
            JOIN cluster_search_docs sd ON sd.cluster_id = c.id
            WHERE c.status = 'active'
              AND sd.search_tsv @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s;
            """,
            (query, query, limit),
        )
        rows = cur.fetchall()

    results = []
    for r in rows:
        results.append(
            VectorSearchResult(
                cluster_id=r["cluster_id"],
                canonical_title=r["canonical_title"],
                takeaway=r["takeaway"],
                similarity_score=float(r["score"]) if r["score"] else 0.0,
            )
        )

    return VectorSearchResponse(
        query=query,
        results=results,
        fallback_to_fts=True,
    )


@router.get("/cache/stats", response_model=CacheStatsResponse)
def get_cache_stats() -> CacheStatsResponse:
    """
    Get cache statistics.

    Returns Redis cache statistics for monitoring.
    """
    r = get_redis_client()
    if r is None:
        return CacheStatsResponse(redis_available=False)

    try:
        info: dict[str, Any] = r.info()  # type: ignore[assignment]
        db0 = info.get("db0")
        keys_count = db0.get("keys") if isinstance(db0, dict) else None
        return CacheStatsResponse(
            redis_available=True,
            keys_count=keys_count,
            memory_used_bytes=info.get("used_memory"),
            uptime_seconds=info.get("uptime_in_seconds"),
        )
    except Exception:
        return CacheStatsResponse(redis_available=False)


@router.delete("/cache/invalidate", response_model=SimpleOkResponse)
def invalidate_cache(
    pattern: str = Query(default="*", description="Key pattern to invalidate"),
    _: None = Depends(require_admin),  # Require admin for cache operations
) -> SimpleOkResponse:
    """
    Invalidate cache entries matching a pattern.

    Admin/dev endpoint to clear cached data.
    """
    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")

    try:
        # Use SCAN to find keys matching pattern (safer than KEYS)
        cursor: int = 0
        deleted = 0
        while True:
            result: tuple[int, list[Any]] = r.scan(  # type: ignore[assignment]
                cursor=cursor, match=pattern, count=100
            )
            cursor = result[0]
            keys: list[Any] = result[1]
            if keys:
                r.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return simple_ok()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
