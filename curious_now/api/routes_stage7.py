"""Stage 7: PWA + Performance + Caching routes.

This module provides endpoints for Progressive Web App functionality,
including offline support, caching hints, and vector search.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from curious_now.api.deps import AuthedUser, get_db, optional_user, require_user
from curious_now.api.schemas import SimpleOkResponse
from curious_now.cache import get_redis_client
from curious_now.repo_stage5 import simple_ok
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


class OfflineCluster(BaseModel):
    """Minimal cluster data for offline storage."""

    model_config = ConfigDict(from_attributes=True)

    cluster_id: UUID
    canonical_title: str
    takeaway: str | None = None
    updated_at: datetime
    topic_names: list[str] = []


class OfflineClustersResponse(BaseModel):
    """Response with clusters for offline storage."""

    model_config = ConfigDict(from_attributes=True)

    clusters: list[OfflineCluster]
    sync_token: str
    generated_at: datetime


class OfflineSyncRequest(BaseModel):
    """Request to sync offline actions."""

    model_config = ConfigDict(from_attributes=True)

    actions: list[dict[str, Any]]
    client_id: UUID | None = None


class OfflineSyncResponse(BaseModel):
    """Response from offline sync."""

    model_config = ConfigDict(from_attributes=True)

    synced_count: int
    failed_count: int
    errors: list[str] = []


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


@router.get("/offline/clusters", response_model=OfflineClustersResponse)
def get_offline_clusters(
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> OfflineClustersResponse:
    """
    Get saved clusters for offline storage.

    Returns the user's saved clusters with minimal data for offline reading.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                c.updated_at,
                COALESCE(
                    array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS topic_names
            FROM user_cluster_saves ucs
            JOIN story_clusters c ON c.id = ucs.cluster_id
            LEFT JOIN cluster_topics ct ON ct.cluster_id = c.id
            LEFT JOIN topics t ON t.id = ct.topic_id
            WHERE ucs.user_id = %s
              AND c.status = 'active'
            GROUP BY c.id, c.canonical_title, c.takeaway, c.updated_at
            ORDER BY ucs.saved_at DESC
            LIMIT %s;
            """,
            (user.user_id, limit),
        )
        rows = cur.fetchall()

    clusters = []
    for r in rows:
        clusters.append(
            OfflineCluster(
                cluster_id=r["cluster_id"],
                canonical_title=r["canonical_title"],
                takeaway=r["takeaway"],
                updated_at=r["updated_at"],
                topic_names=r["topic_names"] or [],
            )
        )

    # Generate sync token from content hash
    content_hash = hashlib.sha256(
        json.dumps([str(c.cluster_id) for c in clusters]).encode()
    ).hexdigest()[:16]
    sync_token = f"{user.user_id}:{content_hash}"

    return OfflineClustersResponse(
        clusters=clusters,
        sync_token=sync_token,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/offline/sync", response_model=OfflineSyncResponse)
def sync_offline_actions(
    request: OfflineSyncRequest,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> OfflineSyncResponse:
    """
    Sync offline actions to the server.

    Processes actions that were queued while offline (saves, hides, etc.).
    """
    synced = 0
    failed = 0
    errors: list[str] = []

    for action in request.actions:
        action_type = action.get("type")
        cluster_id = action.get("cluster_id")
        topic_id = action.get("topic_id")

        try:
            if action_type == "save" and cluster_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_cluster_saves (user_id, cluster_id)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id, cluster_id) DO NOTHING;
                        """,
                        (user.user_id, UUID(cluster_id)),
                    )
                synced += 1

            elif action_type == "unsave" and cluster_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM user_cluster_saves
                        WHERE user_id = %s AND cluster_id = %s;
                        """,
                        (user.user_id, UUID(cluster_id)),
                    )
                synced += 1

            elif action_type == "hide" and cluster_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_cluster_hides (user_id, cluster_id)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id, cluster_id) DO NOTHING;
                        """,
                        (user.user_id, UUID(cluster_id)),
                    )
                synced += 1

            elif action_type == "follow_topic" and topic_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_topic_follows (user_id, topic_id)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id, topic_id) DO NOTHING;
                        """,
                        (user.user_id, UUID(topic_id)),
                    )
                synced += 1

            elif action_type == "unfollow_topic" and topic_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM user_topic_follows
                        WHERE user_id = %s AND topic_id = %s;
                        """,
                        (user.user_id, UUID(topic_id)),
                    )
                synced += 1

            else:
                failed += 1
                errors.append(f"Unknown action type: {action_type}")

        except Exception as exc:
            failed += 1
            errors.append(str(exc))

    return OfflineSyncResponse(
        synced_count=synced,
        failed_count=failed,
        errors=errors[:10],  # Limit error messages
    )


@router.post("/search/semantic", response_model=VectorSearchResponse)
def semantic_search(
    request: VectorSearchRequest,
    user: AuthedUser | None = Depends(optional_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> VectorSearchResponse:
    """
    Perform semantic/vector search using pgvector.

    Falls back to full-text search if vector search is not available.
    """
    # Check if pgvector is available and embeddings exist
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
        # Fall back to FTS
        return _fallback_fts_search(conn, request.query, request.limit)

    # Check if we have embeddings column
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'story_clusters'
                  AND column_name = 'embedding'
            ) AS has_embedding;
            """
        )
        row = cur.fetchone()
        has_embedding = row["has_embedding"] if row else False

    if not has_embedding:
        return _fallback_fts_search(conn, request.query, request.limit)

    # For now, we don't have a way to generate query embeddings,
    # so fall back to FTS. In production, you'd call an embedding API here.
    return _fallback_fts_search(conn, request.query, request.limit)


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
    _: None = Depends(require_user),  # Require auth for cache operations
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
