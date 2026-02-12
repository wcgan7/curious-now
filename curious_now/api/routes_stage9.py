"""Stage 9: Platform Hardening + Search Upgrades routes.

This module provides endpoints for platform health monitoring, rate limit
management, backup/maintenance operations, and search improvements.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict

from curious_now.api.deps import get_db, require_admin
from curious_now.api.schemas import ClusterCard, SimpleOkResponse, simple_ok
from curious_now.cache import get_redis_client

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class HealthCheckResult(BaseModel):
    """Individual health check result."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    status: Literal["healthy", "degraded", "unhealthy"]
    latency_ms: float | None = None
    message: str | None = None


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with all dependencies."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    version: str
    uptime_seconds: float
    checks: list[HealthCheckResult]


class RateLimitInfo(BaseModel):
    """Rate limit information for a key."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    current_count: int
    limit: int
    window_seconds: int
    remaining: int
    reset_at: datetime


class RateLimitListResponse(BaseModel):
    """Response listing rate limit statuses."""

    model_config = ConfigDict(from_attributes=True)

    limits: list[RateLimitInfo]


class MaintenanceStatusResponse(BaseModel):
    """Maintenance mode status."""

    model_config = ConfigDict(from_attributes=True)

    maintenance_mode: bool
    message: str | None = None
    started_at: datetime | None = None
    estimated_end_at: datetime | None = None


class BackupRequest(BaseModel):
    """Request to trigger a backup."""

    model_config = ConfigDict(from_attributes=True)

    backup_type: Literal["full", "incremental"] = "incremental"
    include_logs: bool = False


class BackupResponse(BaseModel):
    """Response from backup trigger."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["started", "queued", "failed"]
    backup_id: str | None = None
    message: str | None = None


class IdentifierSearchResult(BaseModel):
    """Result from identifier-first search."""

    model_config = ConfigDict(from_attributes=True)

    identifier_type: Literal["doi", "arxiv", "pmid"] | None = None
    identifier_value: str | None = None
    cluster_id: UUID | None = None
    canonical_title: str | None = None
    item_id: UUID | None = None
    item_title: str | None = None


class EnhancedSearchResponse(BaseModel):
    """Enhanced search response with identifier matching."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    identifier_match: IdentifierSearchResult | None = None
    clusters: list[ClusterCard]


class AuditLogEntry(BaseModel):
    """An audit log entry (editorial action)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    actor_type: str
    actor_user_id: UUID | None = None
    action_type: str
    target_cluster_id: UUID | None = None
    target_topic_id: UUID | None = None
    notes: str | None = None
    payload: dict[str, Any] | None = None


class AuditLogResponse(BaseModel):
    """Response listing audit log entries."""

    model_config = ConfigDict(from_attributes=True)

    entries: list[AuditLogEntry]
    total_count: int
    offset: int
    limit: int


# ─────────────────────────────────────────────────────────────────────────────
# Global state (for uptime tracking)
# ─────────────────────────────────────────────────────────────────────────────

_START_TIME = time.time()
_MAINTENANCE_MODE = False
_MAINTENANCE_MESSAGE: str | None = None
_MAINTENANCE_STARTED: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Identifier patterns for search
# ─────────────────────────────────────────────────────────────────────────────

# DOI pattern: 10.xxxx/anything
DOI_PATTERN = re.compile(r"^10\.\d{4,}/[^\s]+$", re.IGNORECASE)

# arXiv pattern: YYMM.NNNNN or old format like hep-th/9901001
ARXIV_PATTERN = re.compile(
    r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+/\d{7}(v\d+)?)$", re.IGNORECASE
)

# PubMed ID pattern: just digits
PMID_PATTERN = re.compile(r"^(\d{6,10})$")


def detect_identifier(query: str) -> tuple[str | None, str | None]:
    """
    Detect if a query is a known identifier.

    Returns (identifier_type, normalized_value) or (None, None).
    """
    q = query.strip()

    # Check DOI
    if DOI_PATTERN.match(q):
        return ("doi", q.lower())

    # Check arXiv (also handle arxiv: prefix)
    if q.lower().startswith("arxiv:"):
        q = q[6:].strip()
    if ARXIV_PATTERN.match(q):
        return ("arxiv", q.lower())

    # Check PMID (also handle pmid: prefix)
    if q.lower().startswith("pmid:"):
        q = q[5:].strip()
    if PMID_PATTERN.match(q):
        return ("pmid", q)

    return (None, None)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health/detailed", response_model=DetailedHealthResponse)
def detailed_health_check(
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> DetailedHealthResponse:
    """
    Detailed health check with all dependency statuses.

    Checks database, Redis, and other critical services.
    """
    checks: list[HealthCheckResult] = []
    overall_status: Literal["healthy", "degraded", "unhealthy"] = "healthy"

    # Check database
    db_start = time.time()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        db_latency = (time.time() - db_start) * 1000
        checks.append(
            HealthCheckResult(
                name="database",
                status="healthy",
                latency_ms=round(db_latency, 2),
            )
        )
    except Exception as exc:
        checks.append(
            HealthCheckResult(
                name="database",
                status="unhealthy",
                message=str(exc),
            )
        )
        overall_status = "unhealthy"

    # Check Redis
    r = get_redis_client()
    if r is not None:
        redis_start = time.time()
        try:
            r.ping()
            redis_latency = (time.time() - redis_start) * 1000
            checks.append(
                HealthCheckResult(
                    name="redis",
                    status="healthy",
                    latency_ms=round(redis_latency, 2),
                )
            )
        except Exception as exc:
            checks.append(
                HealthCheckResult(
                    name="redis",
                    status="degraded",
                    message=str(exc),
                )
            )
            if overall_status == "healthy":
                overall_status = "degraded"
    else:
        checks.append(
            HealthCheckResult(
                name="redis",
                status="degraded",
                message="Redis not configured",
            )
        )
        if overall_status == "healthy":
            overall_status = "degraded"

    # Check maintenance mode
    if _MAINTENANCE_MODE:
        checks.append(
            HealthCheckResult(
                name="maintenance",
                status="degraded",
                message=_MAINTENANCE_MESSAGE or "Maintenance mode active",
            )
        )
        if overall_status == "healthy":
            overall_status = "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version="0.1.0",
        uptime_seconds=round(time.time() - _START_TIME, 2),
        checks=checks,
    )


@router.get("/admin/rate-limits", response_model=RateLimitListResponse)
def list_rate_limits(
    _: None = Depends(require_admin),
    prefix: str = Query(default="rl:", description="Key prefix to search"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> RateLimitListResponse:
    """
    List current rate limit statuses.

    Admin endpoint to view rate limiting state.
    """
    r = get_redis_client()
    if r is None:
        return RateLimitListResponse(limits=[])

    try:
        # Scan for rate limit keys
        cursor: int = 0
        keys: list[str] = []
        while True:
            result: tuple[int, list[Any]] = r.scan(  # type: ignore[assignment]
                cursor=cursor, match=f"{prefix}*", count=100
            )
            cursor = result[0]
            batch: list[Any] = result[1]
            keys.extend([k.decode() if isinstance(k, bytes) else k for k in batch])
            if cursor == 0 or len(keys) >= limit:
                break

        limits = []
        for key in keys[:limit]:
            try:
                count = r.get(key)
                if count is not None:
                    count_val = int(count)  # type: ignore[arg-type]

                    limits.append(
                        RateLimitInfo(
                            key=key,
                            current_count=count_val,
                            limit=100,  # Default, could be endpoint-specific
                            window_seconds=60,  # Default
                            remaining=max(0, 100 - count_val),
                            reset_at=datetime.now(timezone.utc),
                        )
                    )
            except (ValueError, TypeError):
                continue

        return RateLimitListResponse(limits=limits)

    except Exception:
        return RateLimitListResponse(limits=[])


@router.delete("/admin/rate-limits/{key}", response_model=SimpleOkResponse)
def reset_rate_limit(
    key: str,
    _: None = Depends(require_admin),
) -> SimpleOkResponse:
    """
    Reset a specific rate limit.

    Admin endpoint to clear rate limit for a specific key.
    """
    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis not available")

    try:
        # Delete both the exact key and pattern match
        r.delete(key)
        return simple_ok()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


@router.get("/admin/maintenance/status", response_model=MaintenanceStatusResponse)
def get_maintenance_status(
    _: None = Depends(require_admin),
) -> MaintenanceStatusResponse:
    """
    Get current maintenance mode status.
    """
    return MaintenanceStatusResponse(
        maintenance_mode=_MAINTENANCE_MODE,
        message=_MAINTENANCE_MESSAGE,
        started_at=_MAINTENANCE_STARTED,
    )


@router.post("/admin/maintenance/enable", response_model=MaintenanceStatusResponse)
def enable_maintenance_mode(
    message: str = Query(default=None, description="Maintenance message to display"),
    _: None = Depends(require_admin),
) -> MaintenanceStatusResponse:
    """
    Enable maintenance mode.

    When enabled, non-critical endpoints may return 503.
    """
    global _MAINTENANCE_MODE, _MAINTENANCE_MESSAGE, _MAINTENANCE_STARTED

    _MAINTENANCE_MODE = True
    _MAINTENANCE_MESSAGE = message
    _MAINTENANCE_STARTED = datetime.now(timezone.utc)

    return MaintenanceStatusResponse(
        maintenance_mode=True,
        message=message,
        started_at=_MAINTENANCE_STARTED,
    )


@router.post("/admin/maintenance/disable", response_model=MaintenanceStatusResponse)
def disable_maintenance_mode(
    _: None = Depends(require_admin),
) -> MaintenanceStatusResponse:
    """
    Disable maintenance mode.
    """
    global _MAINTENANCE_MODE, _MAINTENANCE_MESSAGE, _MAINTENANCE_STARTED

    _MAINTENANCE_MODE = False
    _MAINTENANCE_MESSAGE = None
    _MAINTENANCE_STARTED = None

    return MaintenanceStatusResponse(maintenance_mode=False)


@router.post("/admin/backup", response_model=BackupResponse)
def trigger_backup(
    request: BackupRequest,
    _: None = Depends(require_admin),
) -> BackupResponse:
    """
    Trigger a database backup.

    Note: This is a placeholder. In production, this would trigger
    actual backup procedures (pg_dump, WAL archival, etc.).
    """
    # In a real implementation, this would:
    # 1. Queue a background job for backup
    # 2. Return a backup_id for tracking
    # 3. Store backup metadata in a table

    backup_id = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    return BackupResponse(
        status="queued",
        backup_id=backup_id,
        message=f"Backup queued: type={request.backup_type}, include_logs={request.include_logs}",
    )


@router.get("/admin/audit-log", response_model=AuditLogResponse)
def list_audit_log(
    _: None = Depends(require_admin),
    action_type: str | None = Query(default=None, description="Filter by action type"),
    cluster_id: UUID | None = Query(default=None, description="Filter by cluster ID"),
    topic_id: UUID | None = Query(default=None, description="Filter by topic ID"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AuditLogResponse:
    """
    List audit log entries (editorial actions).

    Admin endpoint to view the audit trail of all editorial and admin actions.
    """
    # Build query with filters
    conditions = []
    params: list[Any] = []

    if action_type:
        conditions.append("action_type = %s")
        params.append(action_type)

    if cluster_id:
        conditions.append("target_cluster_id = %s")
        params.append(cluster_id)

    if topic_id:
        conditions.append("target_topic_id = %s")
        params.append(topic_id)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Get total count
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM editorial_actions {where_clause};",
            params,
        )
        row = cur.fetchone()
        total_count = row[0] if row else 0

    # Get entries
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                id, created_at, actor_type, actor_user_id, action_type,
                target_cluster_id, target_topic_id, notes, payload
            FROM editorial_actions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
            """,
            params,
        )
        rows = cur.fetchall()

    entries = []
    for r in rows:
        entries.append(
            AuditLogEntry(
                id=r["id"],
                created_at=r["created_at"],
                actor_type=r["actor_type"],
                actor_user_id=r["actor_user_id"],
                action_type=r["action_type"],
                target_cluster_id=r["target_cluster_id"],
                target_topic_id=r["target_topic_id"],
                notes=r["notes"],
                payload=r["payload"],
            )
        )

    return AuditLogResponse(
        entries=entries,
        total_count=total_count,
        offset=offset,
        limit=limit,
    )


@router.get("/search/enhanced", response_model=EnhancedSearchResponse)
def enhanced_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> EnhancedSearchResponse:
    """
    Enhanced search with identifier-first matching.

    If the query looks like a DOI, arXiv ID, or PMID, it will first
    attempt to find an exact match before falling back to full-text search.
    """
    identifier_match: IdentifierSearchResult | None = None

    # Check if query is an identifier
    id_type, id_value = detect_identifier(q)

    if id_type and id_value:
        # Try to find exact match by identifier
        with conn.cursor() as cur:
            if id_type == "doi":
                cur.execute(
                    """
                    SELECT i.id AS item_id, i.title AS item_title, i.doi,
                           ci.cluster_id, c.canonical_title
                    FROM items i
                    LEFT JOIN cluster_items ci ON ci.item_id = i.id
                    LEFT JOIN story_clusters c ON c.id = ci.cluster_id
                    WHERE lower(i.doi) = %s
                    LIMIT 1;
                    """,
                    (id_value,),
                )
            elif id_type == "arxiv":
                cur.execute(
                    """
                    SELECT i.id AS item_id, i.title AS item_title, i.arxiv_id,
                           ci.cluster_id, c.canonical_title
                    FROM items i
                    LEFT JOIN cluster_items ci ON ci.item_id = i.id
                    LEFT JOIN story_clusters c ON c.id = ci.cluster_id
                    WHERE lower(i.arxiv_id) = %s
                    LIMIT 1;
                    """,
                    (id_value,),
                )
            elif id_type == "pmid":
                cur.execute(
                    """
                    SELECT i.id AS item_id, i.title AS item_title, i.pmid,
                           ci.cluster_id, c.canonical_title
                    FROM items i
                    LEFT JOIN cluster_items ci ON ci.item_id = i.id
                    LEFT JOIN story_clusters c ON c.id = ci.cluster_id
                    WHERE i.pmid = %s
                    LIMIT 1;
                    """,
                    (id_value,),
                )

            row = cur.fetchone()
            if row:
                identifier_match = IdentifierSearchResult(
                    identifier_type=id_type,  # type: ignore[arg-type]
                    identifier_value=id_value,
                    cluster_id=row["cluster_id"],
                    canonical_title=row["canonical_title"],
                    item_id=row["item_id"],
                    item_title=row["item_title"],
                )

    # Fall back to / also do FTS search
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.updated_at,
                c.takeaway,
                COUNT(DISTINCT ci.item_id) FILTER (
                    WHERE i.source_id IS NOT NULL
                ) AS distinct_source_count,
                ts_rank(sd.search_tsv, plainto_tsquery('english', %s)) AS rank
            FROM story_clusters c
            JOIN cluster_search_docs sd ON sd.cluster_id = c.id
            LEFT JOIN cluster_items ci ON ci.cluster_id = c.id
            LEFT JOIN items i ON i.id = ci.item_id
            WHERE c.status = 'active'
              AND sd.search_tsv @@ plainto_tsquery('english', %s)
            GROUP BY c.id, c.canonical_title, c.updated_at, c.takeaway, sd.search_tsv
            ORDER BY rank DESC
            LIMIT %s;
            """,
            (q, q, limit),
        )
        rows = cur.fetchall()

    clusters = []
    for r in rows:
        clusters.append(
            ClusterCard(
                cluster_id=r["cluster_id"],
                canonical_title=r["canonical_title"],
                updated_at=r["updated_at"],
                distinct_source_count=r["distinct_source_count"] or 0,
                takeaway=r["takeaway"],
            )
        )

    return EnhancedSearchResponse(
        query=q,
        identifier_match=identifier_match,
        clusters=clusters,
    )


@router.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.
    """
    # Import here to avoid circular imports
    from curious_now.metrics import generate_metrics

    metrics_text = generate_metrics()

    return PlainTextResponse(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
