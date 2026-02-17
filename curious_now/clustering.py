from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

_ARXIV_NEW_RE = re.compile(r"\b\d{4}\.\d{4,5}(v\d+)?\b", re.IGNORECASE)
_ARXIV_OLD_RE = re.compile(r"\b[a-z-]+/\d{7}(v\d+)?\b", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


DecisionType = Literal["created_new", "attached_existing"]


@dataclass(frozen=True)
class Thresholds:
    attach_score: float
    high_confidence_attach_score: float
    min_token_overlap: int
    min_title_jaccard: float
    single_token_guard: bool


@dataclass(frozen=True)
class ScoringWeights:
    title_jaccard: float
    time_proximity: float
    token_overlap: float


@dataclass(frozen=True)
class Bonuses:
    new_source_bonus: float


@dataclass(frozen=True)
class ClusteringConfig:
    time_window_days: int
    max_candidates: int
    thresholds: Thresholds
    scoring_weights: ScoringWeights
    bonuses: Bonuses
    time_decay_days: int
    stopwords: set[str]
    rare_token_min_length: int
    allow_short_tokens: set[str]
    search_doc_titles_limit: int = 8


@dataclass(frozen=True)
class ClusterCandidate:
    cluster_id: UUID
    canonical_title: str
    updated_at: datetime


@dataclass(frozen=True)
class ScoreBreakdown:
    jaccard: float
    overlap: int
    time_prox: float
    base_score: float
    new_source_bonus: float
    total_score: float


@dataclass(frozen=True)
class ClusterAssignmentResult:
    item_id: UUID
    decided_cluster_id: UUID
    decision: DecisionType
    candidate_cluster_ids: list[UUID]
    score_breakdown: dict[str, Any]
    threshold_used: float | None


@dataclass(frozen=True)
class ClusterRunResult:
    items_processed: int
    items_attached: int
    clusters_created: int


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _normalize_json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_clustering_config(path: Path | None = None) -> ClusteringConfig:
    p = path or (_repo_root() / "config" / "clustering.v0.json")
    raw = json.loads(p.read_text(encoding="utf-8"))

    thresholds = raw.get("thresholds") or {}
    weights = raw.get("scoringWeights") or {}
    bonuses = raw.get("bonuses") or {}

    allow_short = set(raw.get("allowShortTokens") or ["ai", "ml", "llm", "jwst", "bert"])

    return ClusteringConfig(
        time_window_days=int(raw.get("timeWindowDays", 14)),
        max_candidates=int(raw.get("maxCandidates", 200)),
        thresholds=Thresholds(
            attach_score=float(thresholds.get("attachScore", 0.72)),
            high_confidence_attach_score=float(thresholds.get("highConfidenceAttachScore", 0.82)),
            min_token_overlap=int(thresholds.get("minTokenOverlap", 2)),
            min_title_jaccard=float(thresholds.get("minTitleJaccard", 0.42)),
            single_token_guard=bool(thresholds.get("singleTokenGuard", True)),
        ),
        scoring_weights=ScoringWeights(
            title_jaccard=float(weights.get("titleJaccard", 0.65)),
            time_proximity=float(weights.get("timeProximity", 0.25)),
            token_overlap=float(weights.get("tokenOverlap", 0.10)),
        ),
        bonuses=Bonuses(new_source_bonus=float(bonuses.get("newSourceBonus", 0.04))),
        time_decay_days=int(raw.get("timeDecayDays", 7)),
        stopwords=set(str(x) for x in (raw.get("stopwords") or [])),
        rare_token_min_length=int(raw.get("rareTokenMinLength", 3)),
        allow_short_tokens=allow_short,
        search_doc_titles_limit=int(raw.get("searchDocTitlesLimit", 8) or 8),
    )


def _normalize_text(text: str) -> str:
    s = text.lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def title_tokens(text: str, *, cfg: ClusteringConfig) -> set[str]:
    norm = _normalize_text(text)
    tokens = set()
    for t in re.split(r"[^a-z0-9]+", norm):
        if not t:
            continue
        if t in cfg.stopwords:
            continue
        if len(t) >= cfg.rare_token_min_length or t in cfg.allow_short_tokens:
            tokens.add(t)
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = a & b
    union = a | b
    return float(len(inter)) / float(len(union)) if union else 0.0


def _time_prox(a: datetime, b: datetime, *, time_decay_days: int) -> float:
    dd = abs((a - b).total_seconds()) / 86400.0
    return math.exp(-dd / float(time_decay_days))


def _extract_ids(text: str) -> tuple[str | None, str | None]:
    arxiv = None
    doi = None
    if m := _ARXIV_NEW_RE.search(text):
        arxiv = m.group(0)
    elif m := _ARXIV_OLD_RE.search(text):
        arxiv = m.group(0)
    if m := _DOI_RE.search(text):
        doi = m.group(0)
    return arxiv, doi


def _ensure_item_ids(
    conn: psycopg.Connection[Any],
    *,
    item_id: UUID,
    title: str,
    canonical_url: str,
) -> tuple[str | None, str | None]:
    # Best-effort extraction; only fills missing columns.
    arxiv, doi = _extract_ids(f"{title} {canonical_url}")
    if arxiv is None and doi is None:
        return None, None

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE items
            SET arxiv_id = COALESCE(arxiv_id, %s),
                doi = COALESCE(doi, %s)
            WHERE id = %s
            RETURNING arxiv_id, doi;
            """,
            (arxiv, doi, item_id),
        )
        row = cur.fetchone()
    if not row:
        return arxiv, doi
    return (
        str(_row_get(row, "arxiv_id", 0)) if _row_get(row, "arxiv_id", 0) is not None else None,
        str(_row_get(row, "doi", 1)) if _row_get(row, "doi", 1) is not None else None,
    )


def _find_clusters_by_external_id(
    conn: psycopg.Connection[Any], *, arxiv_id: str | None, doi: str | None
) -> list[ClusterCandidate]:
    if not arxiv_id and not doi:
        return []

    where: list[str] = []
    params: list[Any] = []
    if arxiv_id:
        where.append("i.arxiv_id = %s")
        params.append(arxiv_id)
    if doi:
        where.append("i.doi = %s")
        params.append(doi)
    where_sql = " OR ".join(where)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            JOIN story_clusters c ON c.id = ci.cluster_id
            WHERE c.status IN ('active', 'pending')
              AND ({where_sql})
            ORDER BY c.updated_at DESC
            LIMIT 10;
            """,
            params,
        )
        rows = cur.fetchall()

    out: list[ClusterCandidate] = []
    for r in rows:
        out.append(
            ClusterCandidate(
                cluster_id=UUID(str(_row_get(r, "cluster_id", 0))),
                canonical_title=str(_row_get(r, "canonical_title", 1)),
                updated_at=_row_get(r, "updated_at", 2),
            )
        )
    return out


def _find_clusters_by_title_search(
    conn: psycopg.Connection[Any],
    *,
    query_text: str,
    now_utc: datetime,
    cfg: ClusteringConfig,
) -> list[ClusterCandidate]:
    q = query_text.strip()
    if not q:
        return []
    window_start = now_utc - timedelta(days=cfg.time_window_days)

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH q AS (
              SELECT plainto_tsquery('english', %s) AS tsq
            )
            SELECT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              ts_rank_cd(d.search_tsv, q.tsq) AS rank
            FROM q
            JOIN cluster_search_docs d ON TRUE
            JOIN story_clusters c ON c.id = d.cluster_id
            WHERE c.status IN ('active', 'pending')
              AND c.updated_at >= %s
              AND d.search_tsv @@ q.tsq
            ORDER BY rank DESC, c.updated_at DESC, c.id DESC
            LIMIT %s;
            """,
            (q, window_start, cfg.max_candidates),
        )
        rows = cur.fetchall()

    out: list[ClusterCandidate] = []
    for r in rows:
        out.append(
            ClusterCandidate(
                cluster_id=UUID(str(_row_get(r, "cluster_id", 0))),
                canonical_title=str(_row_get(r, "canonical_title", 1)),
                updated_at=_row_get(r, "updated_at", 2),
            )
        )
    return out


def _cluster_has_source(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, source_id: UUID
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = %s AND i.source_id = %s
            LIMIT 1;
            """,
            (cluster_id, source_id),
        )
        return cur.fetchone() is not None


def _batch_cluster_has_source(
    conn: psycopg.Connection[Any],
    *,
    cluster_ids: list[UUID],
    source_id: UUID,
) -> set[UUID]:
    """Return set of cluster_ids that already contain source_id."""
    if not cluster_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ci.cluster_id
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = ANY(%s::uuid[])
              AND i.source_id = %s;
            """,
            ([str(c) for c in cluster_ids], source_id),
        )
        return {UUID(str(_row_get(r, "cluster_id", 0))) for r in cur.fetchall()}


def _score_candidate(
    conn: psycopg.Connection[Any],
    *,
    item_tokens: set[str],
    item_time: datetime,
    source_id: UUID,
    candidate: ClusterCandidate,
    cfg: ClusteringConfig,
    has_source: bool | None = None,
) -> ScoreBreakdown | None:
    cluster_tokens = title_tokens(candidate.canonical_title, cfg=cfg)
    overlap = len(item_tokens & cluster_tokens)
    jaccard = _jaccard(item_tokens, cluster_tokens)
    if overlap < cfg.thresholds.min_token_overlap:
        return None
    if jaccard < cfg.thresholds.min_title_jaccard:
        return None
    if cfg.thresholds.single_token_guard and overlap == 1:
        return None

    tp = _time_prox(item_time, candidate.updated_at, time_decay_days=cfg.time_decay_days)
    base_score = (
        cfg.scoring_weights.title_jaccard * jaccard
        + cfg.scoring_weights.time_proximity * tp
        + cfg.scoring_weights.token_overlap * min(float(overlap) / 6.0, 1.0)
    )

    if has_source is None:
        has_source = _cluster_has_source(conn, cluster_id=candidate.cluster_id, source_id=source_id)
    bonus = 0.0 if has_source else cfg.bonuses.new_source_bonus
    total = base_score + bonus
    return ScoreBreakdown(
        jaccard=jaccard,
        overlap=overlap,
        time_prox=tp,
        base_score=base_score,
        new_source_bonus=bonus,
        total_score=total,
    )


def _create_cluster(conn: psycopg.Connection[Any], *, title: str, item_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO story_clusters(status, canonical_title, representative_item_id)
            VALUES ('pending', %s, %s)
            RETURNING id;
            """,
            (title, item_id),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("failed to create cluster")
    return UUID(str(_row_get(row, "id", 0)))


def _attach_item(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, item_id: UUID, role: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cluster_items(cluster_id, item_id, role)
            VALUES (%s,%s,%s)
            ON CONFLICT (cluster_id, item_id) DO NOTHING;
            """,
            (cluster_id, item_id, role),
        )


def _recompute_cluster_metrics(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, now_utc: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE story_clusters c
            SET
              item_count = (
                SELECT count(*) FROM cluster_items ci WHERE ci.cluster_id = c.id
              ),
              distinct_source_count = (
                SELECT count(DISTINCT i.source_id)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ),
              distinct_source_type_count = (
                SELECT count(DISTINCT s.source_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                JOIN sources s ON s.id = i.source_id
                WHERE ci.cluster_id = c.id
              ),
              velocity_6h = (
                SELECT count(*)
                FROM cluster_items ci
                WHERE ci.cluster_id = c.id
                  AND ci.added_at >= %s - interval '6 hours'
              ),
              velocity_24h = (
                SELECT count(*)
                FROM cluster_items ci
                WHERE ci.cluster_id = c.id
                  AND ci.added_at >= %s - interval '24 hours'
              ),
              updated_at = %s
            WHERE c.id = %s;
            """,
            (now_utc, now_utc, now_utc, cluster_id),
        )

        cur.execute(
            """
            UPDATE story_clusters
            SET
              recency_score = exp(-EXTRACT(EPOCH FROM (%s - updated_at)) / 86400.0),
              trending_score = (
                (
                  (velocity_6h + 0.5 * velocity_24h) * 1.0
                  + LEAST(distinct_source_count, 10) * 0.3
                )
                * exp(-EXTRACT(EPOCH FROM (%s - updated_at)) / 86400.0)
              )
            WHERE id = %s;
            """,
            (now_utc, now_utc, cluster_id),
        )


def _batch_recompute_cluster_metrics(
    conn: psycopg.Connection[Any],
    *,
    cluster_ids: list[UUID],
    now_utc: datetime,
) -> None:
    """Batch recompute metrics for multiple clusters in a single CTE UPDATE."""
    if not cluster_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH cluster_metrics AS (
              SELECT
                ci.cluster_id,
                count(*) AS item_count,
                count(DISTINCT i.source_id) AS distinct_source_count,
                count(DISTINCT s.source_type) AS distinct_source_type_count,
                count(*) FILTER (WHERE ci.added_at >= %s - interval '6 hours') AS velocity_6h,
                count(*) FILTER (WHERE ci.added_at >= %s - interval '24 hours') AS velocity_24h
              FROM cluster_items ci
              JOIN items i ON i.id = ci.item_id
              JOIN sources s ON s.id = i.source_id
              WHERE ci.cluster_id = ANY(%s::uuid[])
              GROUP BY ci.cluster_id
            )
            UPDATE story_clusters c
            SET
              item_count = cm.item_count,
              distinct_source_count = cm.distinct_source_count,
              distinct_source_type_count = cm.distinct_source_type_count,
              velocity_6h = cm.velocity_6h,
              velocity_24h = cm.velocity_24h,
              updated_at = %s,
              recency_score = exp(-EXTRACT(EPOCH FROM (%s - c.updated_at)) / 86400.0),
              trending_score = (
                (cm.velocity_6h + 0.5 * cm.velocity_24h + LEAST(cm.distinct_source_count, 10) * 0.3)
                * exp(-EXTRACT(EPOCH FROM (%s - c.updated_at)) / 86400.0)
              )
            FROM cluster_metrics cm
            WHERE c.id = cm.cluster_id;
            """,
            (
                now_utc, now_utc,
                [str(c) for c in cluster_ids],
                now_utc, now_utc,
                now_utc,
            ),
        )


def _update_cluster_representative(conn: psycopg.Connection[Any], *, cluster_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              i.id AS item_id,
              i.title,
              i.content_type,
              coalesce(i.published_at, i.fetched_at) AS ts,
              s.reliability_tier
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            JOIN sources s ON s.id = i.source_id
            WHERE ci.cluster_id = %s
            ORDER BY ts DESC
            LIMIT 50;
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()

    best_id: UUID | None = None
    best_title: str | None = None
    best_score = -1e9
    best_ts: datetime | None = None

    for r in rows:
        item_id = UUID(str(_row_get(r, "item_id", 0)))
        title = str(_row_get(r, "title", 1))
        ctype = str(_row_get(r, "content_type", 2))
        ts = _row_get(r, "ts", 3)
        tier = _row_get(r, "reliability_tier", 4)

        score = 0.0
        if ctype == "peer_reviewed":
            score += 2.0
        elif ctype == "preprint":
            score += 1.5
        elif ctype == "report":
            score += 1.0
        elif ctype == "press_release":
            score += 0.5

        if tier == "tier1":
            score += 1.0
        elif tier == "tier2":
            score += 0.5

        tl = len(title)
        if 30 <= tl <= 160:
            score += 1.0
        if title.isupper():
            score -= 1.0

        if best_title is None or score > best_score or (
            score == best_score and ts is not None and (best_ts is None or ts > best_ts)
        ):
            best_score = score
            best_title = title
            best_id = item_id
            best_ts = ts

    if best_id is None or best_title is None:
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE story_clusters
            SET canonical_title = %s,
                representative_item_id = %s
            WHERE id = %s;
            """,
            (best_title, best_id, cluster_id),
        )


def _build_search_text(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, max_titles: int
) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT canonical_title FROM story_clusters WHERE id = %s;", (cluster_id,))
        row = cur.fetchone()
        title = str(_row_get(row, "canonical_title", 0)) if row else ""

        cur.execute(
            """
            SELECT i.title, i.arxiv_id, i.doi
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = %s
            ORDER BY coalesce(i.published_at, i.fetched_at) DESC
            LIMIT %s;
            """,
            (cluster_id, max_titles),
        )
        rows = cur.fetchall()

    titles: list[str] = []
    arxiv_ids: set[str] = set()
    dois: set[str] = set()
    for r in rows:
        t = _row_get(r, "title", 0)
        if isinstance(t, str) and t.strip():
            titles.append(t.strip())
        a = _row_get(r, "arxiv_id", 1)
        if isinstance(a, str) and a.strip():
            arxiv_ids.add(a.strip())
        d = _row_get(r, "doi", 2)
        if isinstance(d, str) and d.strip():
            dois.add(d.strip())

    parts: list[str] = []
    if title:
        parts.append(title)
    parts.extend(titles)
    parts.extend(sorted(arxiv_ids))
    parts.extend(sorted(dois))
    return "\n".join(parts).strip()


def _batch_upsert_search_docs(
    conn: psycopg.Connection[Any],
    *,
    cluster_ids: list[UUID],
    cfg: ClusteringConfig,
    now_utc: datetime,
) -> None:
    """Rebuild search docs for multiple clusters."""
    for cid in cluster_ids:
        text = _build_search_text(conn, cluster_id=cid, max_titles=cfg.search_doc_titles_limit)
        _upsert_search_doc(conn, cluster_id=cid, search_text=text, now_utc=now_utc)


def _upsert_search_doc(
    conn: psycopg.Connection[Any], *, cluster_id: UUID, search_text: str, now_utc: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cluster_search_docs(cluster_id, search_text, updated_at)
            VALUES (%s,%s,%s)
            ON CONFLICT (cluster_id)
            DO UPDATE SET search_text = EXCLUDED.search_text, updated_at = EXCLUDED.updated_at;
            """,
            (cluster_id, search_text, now_utc),
        )


def _emit_update_log_if_meaningful(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    item_id: UUID,
    item_title: str,
    content_type: str,
    source_id: UUID,
) -> None:
    if content_type not in {"peer_reviewed", "preprint", "report"}:
        return
    summary = f"New evidence added: {item_title}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO update_log_entries(
              cluster_id, change_type, summary, diff, supporting_item_ids
            )
            VALUES (%s,'new_evidence',%s,%s,%s);
            """,
            (
                cluster_id,
                summary,
                Jsonb(
                    {
                        "item_id": str(item_id),
                        "content_type": content_type,
                        "source_id": str(source_id),
                    }
                ),
                Jsonb([str(item_id)]),
            ),
        )


def assign_item_to_cluster(
    conn: psycopg.Connection[Any],
    *,
    item_id: UUID,
    cfg: ClusteringConfig,
    now_utc: datetime | None = None,
    defer_metrics: bool = False,
) -> ClusterAssignmentResult | None:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              i.id AS item_id,
              i.source_id,
              i.title,
              i.canonical_url,
              coalesce(i.published_at, i.fetched_at) AS item_time,
              i.content_type,
              i.arxiv_id,
              i.doi
            FROM items i
            WHERE i.id = %s;
            """,
            (item_id,),
        )
        row = cur.fetchone()
    if not row:
        return None

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM cluster_items WHERE item_id = %s LIMIT 1;", (item_id,))
        if cur.fetchone() is not None:
            return None

    source_id = UUID(str(_row_get(row, "source_id", 1)))
    title = str(_row_get(row, "title", 2))
    canonical_url = str(_row_get(row, "canonical_url", 3))
    item_time = _row_get(row, "item_time", 4)
    content_type = str(_row_get(row, "content_type", 5))
    arxiv_id = _row_get(row, "arxiv_id", 6)
    doi = _row_get(row, "doi", 7)

    arxiv, doi2 = _ensure_item_ids(conn, item_id=item_id, title=title, canonical_url=canonical_url)
    if arxiv_id is None:
        arxiv_id = arxiv
    if doi is None:
        doi = doi2

    candidates_by_id = _find_clusters_by_external_id(conn, arxiv_id=arxiv_id, doi=doi)
    candidate_ids: list[UUID] = [c.cluster_id for c in candidates_by_id]
    if candidates_by_id:
        decided_cluster = candidates_by_id[0].cluster_id
        decision: DecisionType = "attached_existing"
        with conn.transaction():
            _attach_item(conn, cluster_id=decided_cluster, item_id=item_id, role="supporting")
            _update_cluster_representative(conn, cluster_id=decided_cluster)
            if not defer_metrics:
                _recompute_cluster_metrics(conn, cluster_id=decided_cluster, now_utc=now)
                search_text = _build_search_text(
                    conn, cluster_id=decided_cluster, max_titles=cfg.search_doc_titles_limit
                )
                _upsert_search_doc(
                    conn, cluster_id=decided_cluster, search_text=search_text, now_utc=now
                )
            _emit_update_log_if_meaningful(
                conn,
                cluster_id=decided_cluster,
                item_id=item_id,
                item_title=title,
                content_type=content_type,
                source_id=source_id,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cluster_assignment_logs(
                      item_id,
                      decided_cluster_id,
                      decision,
                      candidate_cluster_ids,
                      score_breakdown,
                      threshold_used
                    )
                    VALUES (%s,%s,'attached_existing',%s,%s,%s);
                    """,
                    (
                        item_id,
                        decided_cluster,
                        Jsonb([str(x) for x in candidate_ids]),
                        Jsonb({"external_id_match": True, "arxiv_id": arxiv_id, "doi": doi}),
                        None,
                    ),
                )
        return ClusterAssignmentResult(
            item_id=item_id,
            decided_cluster_id=decided_cluster,
            decision=decision,
            candidate_cluster_ids=candidate_ids,
            score_breakdown={"external_id_match": True, "arxiv_id": arxiv_id, "doi": doi},
            threshold_used=None,
        )

    # Text candidates via FTS
    item_tokens = title_tokens(title, cfg=cfg)
    qtext = " ".join(sorted(item_tokens))
    candidates = _find_clusters_by_title_search(conn, query_text=qtext, now_utc=now, cfg=cfg)

    # Batch source-check: 1 query instead of N per candidate
    candidate_ids = [c.cluster_id for c in candidates]
    clusters_with_source = _batch_cluster_has_source(
        conn, cluster_ids=candidate_ids, source_id=source_id
    )

    best_cluster: UUID | None = None
    best_score: ScoreBreakdown | None = None
    scored_ids: list[UUID] = []

    for c in candidates:
        sb = _score_candidate(
            conn,
            item_tokens=item_tokens,
            item_time=item_time,
            source_id=source_id,
            candidate=c,
            cfg=cfg,
            has_source=(c.cluster_id in clusters_with_source),
        )
        if sb is None:
            continue
        scored_ids.append(c.cluster_id)
        if best_score is None or sb.total_score > best_score.total_score:
            best_score = sb
            best_cluster = c.cluster_id

    if (
        best_cluster is not None
        and best_score is not None
        and best_score.total_score >= cfg.thresholds.attach_score
    ):
        with conn.transaction():
            _attach_item(conn, cluster_id=best_cluster, item_id=item_id, role="supporting")
            _update_cluster_representative(conn, cluster_id=best_cluster)
            if not defer_metrics:
                _recompute_cluster_metrics(conn, cluster_id=best_cluster, now_utc=now)
                search_text = _build_search_text(
                    conn, cluster_id=best_cluster, max_titles=cfg.search_doc_titles_limit
                )
                _upsert_search_doc(conn, cluster_id=best_cluster, search_text=search_text, now_utc=now)
            _emit_update_log_if_meaningful(
                conn,
                cluster_id=best_cluster,
                item_id=item_id,
                item_title=title,
                content_type=content_type,
                source_id=source_id,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cluster_assignment_logs(
                      item_id,
                      decided_cluster_id,
                      decision,
                      candidate_cluster_ids,
                      score_breakdown,
                      threshold_used
                    )
                    VALUES (%s,%s,'attached_existing',%s,%s,%s);
                    """,
                    (
                        item_id,
                        best_cluster,
                        Jsonb([str(x) for x in scored_ids]),
                        Jsonb(best_score.__dict__),
                        cfg.thresholds.attach_score,
                    ),
                )
        return ClusterAssignmentResult(
            item_id=item_id,
            decided_cluster_id=best_cluster,
            decision="attached_existing",
            candidate_cluster_ids=scored_ids,
            score_breakdown=best_score.__dict__,
            threshold_used=cfg.thresholds.attach_score,
        )

    # Otherwise: create new cluster.
    with conn.transaction():
        new_cluster = _create_cluster(conn, title=title, item_id=item_id)
        _attach_item(conn, cluster_id=new_cluster, item_id=item_id, role="primary")
        _update_cluster_representative(conn, cluster_id=new_cluster)
        if not defer_metrics:
            _recompute_cluster_metrics(conn, cluster_id=new_cluster, now_utc=now)
            search_text = _build_search_text(
                conn, cluster_id=new_cluster, max_titles=cfg.search_doc_titles_limit
            )
            _upsert_search_doc(conn, cluster_id=new_cluster, search_text=search_text, now_utc=now)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cluster_assignment_logs(
                  item_id,
                  decided_cluster_id,
                  decision,
                  candidate_cluster_ids,
                  score_breakdown,
                  threshold_used
                )
                VALUES (%s,%s,'created_new',%s,%s,%s);
                """,
                (
                    item_id,
                    new_cluster,
                    Jsonb([str(x) for x in scored_ids]),
                    Jsonb(best_score.__dict__ if best_score else {}),
                    cfg.thresholds.attach_score,
                ),
            )

    return ClusterAssignmentResult(
        item_id=item_id,
        decided_cluster_id=new_cluster,
        decision="created_new",
        candidate_cluster_ids=scored_ids,
        score_breakdown=best_score.__dict__ if best_score else {},
        threshold_used=cfg.thresholds.attach_score,
    )


def cluster_unassigned_items(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    limit_items: int = 500,
    cfg: ClusteringConfig | None = None,
) -> ClusterRunResult:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    config = cfg or load_clustering_config()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id
            FROM items i
            WHERE NOT EXISTS (SELECT 1 FROM cluster_items ci WHERE ci.item_id = i.id)
            ORDER BY coalesce(i.published_at, i.fetched_at) ASC, i.id ASC
            LIMIT %s;
            """,
            (limit_items,),
        )
        rows = cur.fetchall()
    item_ids = [UUID(str(_row_get(r, "id", 0))) for r in rows]

    processed = 0
    attached = 0
    created = 0
    dirty_cluster_ids: set[UUID] = set()
    for iid in item_ids:
        res = assign_item_to_cluster(conn, item_id=iid, cfg=config, now_utc=now, defer_metrics=True)
        if res is None:
            continue
        processed += 1
        dirty_cluster_ids.add(res.decided_cluster_id)
        if res.decision == "created_new":
            created += 1
        else:
            attached += 1

    # Batch recompute metrics for all dirty clusters
    if dirty_cluster_ids:
        _batch_recompute_cluster_metrics(
            conn, cluster_ids=list(dirty_cluster_ids), now_utc=now
        )
        # Batch rebuild search docs
        _batch_upsert_search_docs(conn, cluster_ids=list(dirty_cluster_ids), cfg=config, now_utc=now)

    return ClusterRunResult(
        items_processed=processed, items_attached=attached, clusters_created=created
    )


def recompute_trending(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    lookback_days: int = 14,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    window_start = now - timedelta(days=lookback_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH metrics AS (
              SELECT
                c.id,
                (SELECT count(*) FROM cluster_items ci
                 WHERE ci.cluster_id = c.id AND ci.added_at >= %s - interval '6 hours') AS v6h,
                (SELECT count(*) FROM cluster_items ci
                 WHERE ci.cluster_id = c.id AND ci.added_at >= %s - interval '24 hours') AS v24h,
                (SELECT count(DISTINCT i.source_id)
                 FROM cluster_items ci JOIN items i ON i.id = ci.item_id
                 WHERE ci.cluster_id = c.id) AS src_count,
                exp(-EXTRACT(EPOCH FROM (%s - c.updated_at)) / 86400.0) AS decay
              FROM story_clusters c
              WHERE c.status IN ('active', 'pending') AND c.updated_at >= %s
            )
            UPDATE story_clusters c
            SET
              velocity_6h = m.v6h,
              velocity_24h = m.v24h,
              distinct_source_count = m.src_count,
              recency_score = m.decay,
              trending_score = (
                (m.v6h + 0.5 * m.v24h + LEAST(m.src_count, 10) * 0.3) * m.decay
              )
            FROM metrics m
            WHERE c.id = m.id;
            """,
            (now, now, now, window_start),
        )
        return int(cur.rowcount)


def promote_pending_clusters(
    conn: psycopg.Connection[Any],
) -> int:
    """Promote pending clusters to active once they meet readiness criteria.

    A cluster is promoted when ALL of:
    1. takeaway IS NOT NULL
    2. summary_intuition IS NOT NULL
    3. Has at least one topic tag

    Returns the number of clusters promoted.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE story_clusters
            SET status = 'active', updated_at = now()
            WHERE status = 'pending'
              AND takeaway IS NOT NULL
              AND summary_intuition IS NOT NULL
              AND EXISTS (SELECT 1 FROM cluster_topics ct WHERE ct.cluster_id = id)
            RETURNING id;
            """
        )
        promoted = cur.fetchall()
    promoted_ids = [UUID(str(_row_get(r, "id", 0))) for r in promoted]
    if promoted_ids:
        logger.info("Promoted %d pending clusters to active: %s", len(promoted_ids), promoted_ids)
    return len(promoted_ids)
