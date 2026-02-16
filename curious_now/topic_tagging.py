from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CategorySeed:
    """V1 format: top-level category."""

    name: str
    description_short: str | None
    aliases: list[str]


@dataclass(frozen=True)
class SubtopicSeed:
    """V1 format: subtopic belonging to a category."""

    name: str
    category_name: str  # References CategorySeed.name
    aliases: list[str]


@dataclass(frozen=True)
class TopicSeedV1:
    """V1 format: 2-layer hierarchy with categories and subtopics."""

    categories: list[CategorySeed]
    subtopics: list[SubtopicSeed]


@dataclass(frozen=True)
class TopicDef:
    topic_id: UUID
    name: str
    description_short: str | None
    aliases: list[str]


@dataclass(frozen=True)
class TopicTaggingResult:
    clusters_scanned: int
    clusters_updated: int


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def load_topic_seed_v1(path: Path | None = None) -> TopicSeedV1:
    """Load topics from v1 format (2-layer: categories + subtopics)."""
    p = path or (_repo_root() / "config" / "topics.seed.v1.json")
    raw = json.loads(p.read_text(encoding="utf-8"))

    categories_raw = raw.get("categories")
    if not isinstance(categories_raw, list):
        raise ValueError("topics.seed.v1.json must contain a 'categories' array")

    subtopics_raw = raw.get("subtopics")
    if not isinstance(subtopics_raw, list):
        raise ValueError("topics.seed.v1.json must contain a 'subtopics' array")

    categories: list[CategorySeed] = []
    for c in categories_raw:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        aliases_raw = c.get("aliases")
        aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
        categories.append(
            CategorySeed(
                name=" ".join(name.split()),
                description_short=(
                    " ".join(str(c.get("description_short")).split())
                    if isinstance(c.get("description_short"), str)
                    else None
                ),
                aliases=[a for a in (" ".join(x.split()) for x in aliases) if a],
            )
        )

    subtopics: list[SubtopicSeed] = []
    for s in subtopics_raw:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        category = s.get("category")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(category, str) or not category.strip():
            continue
        aliases_raw = s.get("aliases")
        aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
        subtopics.append(
            SubtopicSeed(
                name=" ".join(name.split()),
                category_name=" ".join(category.split()),
                aliases=[a for a in (" ".join(x.split()) for x in aliases) if a],
            )
        )

    return TopicSeedV1(categories=categories, subtopics=subtopics)


@dataclass(frozen=True)
class TopicSeedV1Result:
    """Result of seeding v1 topics."""

    categories_inserted: int
    categories_updated: int
    subtopics_inserted: int
    subtopics_updated: int


def seed_topics_v1(
    conn: psycopg.Connection[Any],
    *,
    seed: TopicSeedV1,
    now_utc: datetime | None = None,
) -> TopicSeedV1Result:
    """
    Seed topics from v1 format (2-layer hierarchy).

    Categories are inserted first with parent_topic_id=NULL.
    Subtopics are inserted with parent_topic_id pointing to their category.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    categories_inserted = 0
    categories_updated = 0
    subtopics_inserted = 0
    subtopics_updated = 0

    # Map category names to IDs for linking subtopics
    category_name_to_id: dict[str, UUID] = {}

    with conn.cursor() as cur:
        # Step 1: Upsert categories (parent_topic_id = NULL)
        for cat in seed.categories:
            cur.execute(
                """
                INSERT INTO topics(name, description_short, aliases, parent_topic_id, updated_at)
                VALUES (%s, %s, %s, NULL, %s)
                ON CONFLICT (name)
                DO UPDATE SET
                  description_short = EXCLUDED.description_short,
                  aliases = EXCLUDED.aliases,
                  parent_topic_id = NULL,
                  updated_at = EXCLUDED.updated_at
                RETURNING id, (xmax = 0) AS inserted;
                """,
                (cat.name, cat.description_short, Jsonb(cat.aliases), now),
            )
            row = cur.fetchone()
            if row:
                topic_id = UUID(str(_row_get(row, "id", 0)))
                category_name_to_id[cat.name] = topic_id
                if bool(_row_get(row, "inserted", 1)):
                    categories_inserted += 1
                else:
                    categories_updated += 1

        # Step 2: Upsert subtopics with parent_topic_id pointing to category
        for sub in seed.subtopics:
            parent_id = category_name_to_id.get(sub.category_name)
            if parent_id is None:
                logger.warning(
                    "Subtopic '%s' references unknown category '%s', skipping",
                    sub.name,
                    sub.category_name,
                )
                continue

            cur.execute(
                """
                INSERT INTO topics(name, description_short, aliases, parent_topic_id, updated_at)
                VALUES (%s, NULL, %s, %s, %s)
                ON CONFLICT (name)
                DO UPDATE SET
                  aliases = EXCLUDED.aliases,
                  parent_topic_id = EXCLUDED.parent_topic_id,
                  updated_at = EXCLUDED.updated_at
                RETURNING (xmax = 0) AS inserted;
                """,
                (sub.name, Jsonb(sub.aliases), parent_id, now),
            )
            row = cur.fetchone()
            if row and bool(_row_get(row, "inserted", 0)):
                subtopics_inserted += 1
            else:
                subtopics_updated += 1

    return TopicSeedV1Result(
        categories_inserted=categories_inserted,
        categories_updated=categories_updated,
        subtopics_inserted=subtopics_inserted,
        subtopics_updated=subtopics_updated,
    )


def _load_topics(conn: psycopg.Connection[Any]) -> list[TopicDef]:
    """Load all topics (both categories and subtopics)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, description_short, aliases FROM topics ORDER BY name ASC;")
        rows = cur.fetchall()

    out: list[TopicDef] = []
    for r in rows:
        aliases = [str(x) for x in _normalize_json_array(_row_get(r, "aliases", 3))]
        out.append(
            TopicDef(
                topic_id=UUID(str(_row_get(r, "id", 0))),
                name=str(_row_get(r, "name", 1)),
                description_short=(
                    str(_row_get(r, "description_short", 2))
                    if _row_get(r, "description_short", 2) is not None
                    else None
                ),
                aliases=[a for a in (x.strip() for x in aliases) if a],
            )
        )
    return out


def _load_subtopics(conn: psycopg.Connection[Any]) -> list[TopicDef]:
    """Load only subtopics (topics with a parent_topic_id)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, description_short, aliases
            FROM topics
            WHERE parent_topic_id IS NOT NULL
            ORDER BY name ASC;
            """
        )
        rows = cur.fetchall()

    out: list[TopicDef] = []
    for r in rows:
        aliases = [str(x) for x in _normalize_json_array(_row_get(r, "aliases", 3))]
        out.append(
            TopicDef(
                topic_id=UUID(str(_row_get(r, "id", 0))),
                name=str(_row_get(r, "name", 1)),
                description_short=(
                    str(_row_get(r, "description_short", 2))
                    if _row_get(r, "description_short", 2) is not None
                    else None
                ),
                aliases=[a for a in (x.strip() for x in aliases) if a],
            )
        )
    return out


def _load_categories(conn: psycopg.Connection[Any]) -> list[TopicDef]:
    """Load only categories (topics without a parent_topic_id)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, description_short, aliases
            FROM topics
            WHERE parent_topic_id IS NULL
            ORDER BY name ASC;
            """
        )
        rows = cur.fetchall()

    out: list[TopicDef] = []
    for r in rows:
        aliases = [str(x) for x in _normalize_json_array(_row_get(r, "aliases", 3))]
        out.append(
            TopicDef(
                topic_id=UUID(str(_row_get(r, "id", 0))),
                name=str(_row_get(r, "name", 1)),
                description_short=(
                    str(_row_get(r, "description_short", 2))
                    if _row_get(r, "description_short", 2) is not None
                    else None
                ),
                aliases=[a for a in (x.strip() for x in aliases) if a],
            )
        )
    return out


@dataclass(frozen=True)
class CategoryInfo:
    """Category derived from subtopic assignments."""

    category_id: UUID
    category_name: str
    max_subtopic_score: float
    subtopic_count: int


def get_cluster_categories(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
) -> list[CategoryInfo]:
    """
    Derive categories from a cluster's subtopic assignments.

    Returns categories ordered by the max score of their subtopics.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                cat.id AS category_id,
                cat.name AS category_name,
                MAX(ct.score) AS max_score,
                COUNT(ct.topic_id) AS subtopic_count
            FROM cluster_topics ct
            JOIN topics sub ON sub.id = ct.topic_id
            JOIN topics cat ON cat.id = sub.parent_topic_id
            WHERE ct.cluster_id = %s
              AND sub.parent_topic_id IS NOT NULL
            GROUP BY cat.id, cat.name
            ORDER BY max_score DESC, cat.name ASC;
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()

    return [
        CategoryInfo(
            category_id=UUID(str(_row_get(r, "category_id", 0))),
            category_name=str(_row_get(r, "category_name", 1)),
            max_subtopic_score=float(_row_get(r, "max_score", 2)),
            subtopic_count=int(_row_get(r, "subtopic_count", 3)),
        )
        for r in rows
    ]


def has_subtopics(conn: psycopg.Connection[Any]) -> bool:
    """Check if the topics table has any subtopics (v1 format)."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM topics WHERE parent_topic_id IS NOT NULL LIMIT 1;")
        return cur.fetchone() is not None


def _get_cluster_text(
    conn: psycopg.Connection[Any], *, cluster_id: UUID
) -> tuple[str, str] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.canonical_title, d.search_text
            FROM story_clusters c
            LEFT JOIN cluster_search_docs d ON d.cluster_id = c.id
            WHERE c.id = %s AND c.status = 'active';
            """,
            (cluster_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    title = str(_row_get(row, "canonical_title", 0) or "")
    search_text = str(_row_get(row, "search_text", 1) or title)
    return title, search_text


def _get_cluster_text_batch(
    conn: psycopg.Connection[Any],
    cluster_ids: list[UUID],
) -> dict[UUID, tuple[str, str]]:
    """Fetch (title, search_text) for multiple clusters in one query."""
    if not cluster_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.canonical_title, d.search_text
            FROM story_clusters c
            LEFT JOIN cluster_search_docs d ON d.cluster_id = c.id
            WHERE c.id = ANY(%s::uuid[]) AND c.status = 'active';
            """,
            ([str(c) for c in cluster_ids],),
        )
        rows = cur.fetchall()

    result: dict[UUID, tuple[str, str]] = {}
    for r in rows:
        cid = UUID(str(_row_get(r, "id", 0)))
        title = str(_row_get(r, "canonical_title", 1) or "")
        search_text = str(_row_get(r, "search_text", 2) or title)
        result[cid] = (title, search_text)
    return result


def tag_cluster_topics(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    topics: list[TopicDef],
    now_utc: datetime | None = None,
    max_topics: int = 3,
) -> bool:
    """Tag a single cluster using LLM-only classification."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    cluster_text = _get_cluster_text(conn, cluster_id=cluster_id)
    if cluster_text is None:
        return False
    title, search_text = cluster_text

    assignments = _llm_assignments_for_cluster(
        title=title,
        search_text=search_text,
        topics=topics,
        max_topics=max_topics,
    )
    if not assignments:
        return False
    return _apply_topic_assignments(
        conn,
        cluster_id=cluster_id,
        assignments=assignments,
        assignment_source="llm",
        now_utc=now,
        replace_all_unlocked=True,
    )


def tag_recent_clusters(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    lookback_days: int = 14,
    limit_clusters: int = 500,
    max_topics_per_cluster: int = 3,
) -> TopicTaggingResult:
    """
    Tag recent clusters using LLM-only classification.

    This is the default production tagging path.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    since = now - timedelta(days=int(lookback_days))

    topics = _load_subtopics(conn) if has_subtopics(conn) else _load_topics(conn)

    if not topics:
        return TopicTaggingResult(clusters_scanned=0, clusters_updated=0)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM story_clusters
            WHERE status = 'active'
              AND updated_at >= %s
            ORDER BY updated_at DESC, id DESC
            LIMIT %s;
            """,
            (since, limit_clusters),
        )
        rows = cur.fetchall()

    cluster_ids = [UUID(str(_row_get(r, "id", 0))) for r in rows]

    # Batch-fetch cluster text for all clusters
    text_map = _get_cluster_text_batch(conn, cluster_ids)

    scanned = 0
    updated = 0
    for cid in cluster_ids:
        scanned += 1
        cluster_text = text_map.get(cid)
        if cluster_text is None:
            continue
        title, search_text = cluster_text
        llm_assignments = _llm_assignments_for_cluster(
            title=title,
            search_text=search_text,
            topics=topics,
            max_topics=max_topics_per_cluster,
        )
        if not llm_assignments:
            continue
        if _apply_topic_assignments(
            conn,
            cluster_id=cid,
            assignments=llm_assignments,
            assignment_source="llm",
            now_utc=now,
            replace_all_unlocked=True,
        ):
            updated += 1

    return TopicTaggingResult(clusters_scanned=scanned, clusters_updated=updated)


def _apply_topic_assignments(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    assignments: list[tuple[UUID, float]],
    assignment_source: str,
    now_utc: datetime,
    replace_all_unlocked: bool = False,
) -> bool:
    """Apply topic assignments to a cluster."""
    selected_ids = [tid for (tid, _) in assignments]
    change_count = 0

    with conn.transaction():
        with conn.cursor() as cur:
            # Remove unlocked assignments not in new list.
            # LLM-only default uses replace_all_unlocked=True to fully refresh
            # non-editor assignments.
            if replace_all_unlocked:
                cur.execute(
                    """
                    DELETE FROM cluster_topics
                    WHERE cluster_id = %s
                      AND locked = false
                      AND NOT (topic_id = ANY(%s::uuid[]));
                    """,
                    (cluster_id, selected_ids),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM cluster_topics
                    WHERE cluster_id = %s
                      AND assignment_source = %s
                      AND locked = false
                      AND NOT (topic_id = ANY(%s::uuid[]));
                    """,
                    (cluster_id, assignment_source, selected_ids),
                )
            change_count += int(cur.rowcount)

            # Upsert new assignments
            for topic_id, score in assignments:
                cur.execute(
                    """
                    INSERT INTO cluster_topics(
                      cluster_id, topic_id, score, assignment_source, locked
                    )
                    VALUES (%s,%s,%s,%s,false)
                    ON CONFLICT (cluster_id, topic_id)
                    DO UPDATE SET
                      score = EXCLUDED.score,
                      assignment_source = EXCLUDED.assignment_source
                    WHERE cluster_topics.locked = false;
                    """,
                    (cluster_id, topic_id, float(score), assignment_source),
                )
                change_count += int(cur.rowcount)

            if change_count > 0:
                cur.execute(
                    "UPDATE story_clusters SET updated_at = %s WHERE id = %s;",
                    (now_utc, cluster_id),
                )

    return change_count > 0


def _llm_assignments_for_cluster(
    *,
    title: str,
    search_text: str,
    topics: list[TopicDef],
    max_topics: int,
) -> list[tuple[UUID, float]]:
    from curious_now.ai.topic_classification import TopicDefinition, classify_topics

    topic_defs = [TopicDefinition(name=t.name, description=t.description_short) for t in topics]
    result = classify_topics(
        title=title,
        content=search_text,
        available_topics=topic_defs,
    )
    if not result.success or not result.topics:
        return []

    name_to_id = {t.name: t.topic_id for t in topics}
    assignments: list[tuple[UUID, float]] = []
    for match in result.topics[:max_topics]:
        topic_id = name_to_id.get(match.topic_name)
        if topic_id:
            assignments.append((topic_id, float(match.score)))
    return assignments


def tag_untagged_clusters_llm(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    limit_clusters: int = 100,
    max_topics_per_cluster: int = 3,
) -> TopicTaggingResult:
    """
    Tag clusters that have no topics using LLM only.

    Useful for backfilling clusters that were previously untagged.

    Args:
        conn: Database connection
        now_utc: Current timestamp
        limit_clusters: Maximum clusters to process
        max_topics_per_cluster: Maximum topics per cluster

    Returns:
        TopicTaggingResult with counts
    """
    from curious_now.ai.topic_classification import (
        TopicDefinition,
        classify_topics,
    )

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    # Use subtopics if v1 format is present, otherwise use all topics
    if has_subtopics(conn):
        topics = _load_subtopics(conn)
    else:
        topics = _load_topics(conn)

    if not topics:
        return TopicTaggingResult(clusters_scanned=0, clusters_updated=0)

    # Find clusters with no topic assignments
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id
            FROM story_clusters c
            WHERE c.status = 'active'
              AND NOT EXISTS (
                SELECT 1 FROM cluster_topics ct
                WHERE ct.cluster_id = c.id
                LIMIT 1
              )
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit_clusters,),
        )
        rows = cur.fetchall()

    cluster_ids = [UUID(str(_row_get(r, "id", 0))) for r in rows]
    scanned = 0
    updated = 0

    topic_defs = [
        TopicDefinition(name=t.name, description=t.description_short)
        for t in topics
    ]
    name_to_id = {t.name: t.topic_id for t in topics}

    # Batch-fetch cluster text for all clusters
    text_map = _get_cluster_text_batch(conn, cluster_ids)

    for cid in cluster_ids:
        scanned += 1

        cluster_text = text_map.get(cid)
        if cluster_text is None:
            continue

        title, search_text = cluster_text

        result = classify_topics(
            title=title,
            content=search_text,
            available_topics=topic_defs,
        )

        if not result.success or not result.topics:
            continue

        assignments: list[tuple[UUID, float]] = []
        for match in result.topics[:max_topics_per_cluster]:
            topic_id = name_to_id.get(match.topic_name)
            if topic_id:
                assignments.append((topic_id, match.score))

        if assignments:
            was_updated = _apply_topic_assignments(
                conn,
                cluster_id=cid,
                assignments=assignments,
                assignment_source="auto",
                now_utc=now,
            )
            if was_updated:
                updated += 1

    return TopicTaggingResult(clusters_scanned=scanned, clusters_updated=updated)


# ─────────────────────────────────────────────────────────────────────────────
# Backfill / Migration
# ─────────────────────────────────────────────────────────────────────────────


def clear_auto_topic_assignments(conn: psycopg.Connection[Any]) -> int:
    """
    Clear all auto-assigned topic assignments (keeps editor/locked).

    Returns the number of assignments deleted.
    """
    with conn.cursor() as cur:
        # Only use 'auto' since 'auto_llm' may not exist in enum yet
        cur.execute(
            """
            DELETE FROM cluster_topics
            WHERE assignment_source = 'auto'
              AND locked = false;
            """
        )
        return int(cur.rowcount)


@dataclass(frozen=True)
class BackfillResult:
    """Result of backfilling topics."""

    categories_inserted: int
    categories_updated: int
    subtopics_inserted: int
    subtopics_updated: int
    old_assignments_cleared: int
    clusters_tagged: int
    clusters_scanned: int


def backfill_topics_v1(
    conn: psycopg.Connection[Any],
    *,
    seed: TopicSeedV1,
    now_utc: datetime | None = None,
    limit_clusters: int = 10000,
    max_topics_per_cluster: int = 3,
) -> BackfillResult:
    """
    Full backfill: seed v1 topics, clear old assignments, re-tag all clusters.

    Args:
        conn: Database connection
        seed: V1 topic seed data
        now_utc: Current timestamp
        limit_clusters: Maximum clusters to process
        max_topics_per_cluster: Maximum topics per cluster

    Returns:
        BackfillResult with counts
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    # Step 1: Seed v1 topics
    seed_result = seed_topics_v1(conn, seed=seed, now_utc=now)

    # Step 2: Clear old auto-assignments
    cleared = clear_auto_topic_assignments(conn)

    # Step 3: Re-tag all active clusters with subtopics
    subtopics = _load_subtopics(conn)
    if not subtopics:
        return BackfillResult(
            categories_inserted=seed_result.categories_inserted,
            categories_updated=seed_result.categories_updated,
            subtopics_inserted=seed_result.subtopics_inserted,
            subtopics_updated=seed_result.subtopics_updated,
            old_assignments_cleared=cleared,
            clusters_tagged=0,
            clusters_scanned=0,
        )

    # Get all active clusters
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM story_clusters
            WHERE status = 'active'
            ORDER BY updated_at DESC
            LIMIT %s;
            """,
            (limit_clusters,),
        )
        rows = cur.fetchall()

    cluster_ids = [UUID(str(_row_get(r, "id", 0))) for r in rows]
    scanned = 0
    tagged = 0

    for cid in cluster_ids:
        scanned += 1
        if tag_cluster_topics(
            conn,
            cluster_id=cid,
            topics=subtopics,
            now_utc=now,
            max_topics=max_topics_per_cluster,
        ):
            tagged += 1

    return BackfillResult(
        categories_inserted=seed_result.categories_inserted,
        categories_updated=seed_result.categories_updated,
        subtopics_inserted=seed_result.subtopics_inserted,
        subtopics_updated=seed_result.subtopics_updated,
        old_assignments_cleared=cleared,
        clusters_tagged=tagged,
        clusters_scanned=scanned,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Maintenance: search_text rebuild, low-content filtering, out-of-domain
# ─────────────────────────────────────────────────────────────────────────────

MIN_CONTENT_LENGTH = 100  # Minimum chars for meaningful tagging


@dataclass(frozen=True)
class SearchTextRebuildResult:
    """Result of rebuilding search_text."""

    clusters_scanned: int
    clusters_rebuilt: int


def rebuild_cluster_search_text(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
) -> bool:
    """
    Rebuild search_text for a cluster from its items' titles and full_text.

    Returns True if search_text was updated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cluster_search_docs (cluster_id, search_text)
            SELECT
                ci.cluster_id,
                string_agg(
                    COALESCE(i.title, '') || ' ' || COALESCE(i.snippet, '') || ' ' || COALESCE(i.full_text, ''),
                    ' '
                )
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = %s
            GROUP BY ci.cluster_id
            ON CONFLICT (cluster_id)
            DO UPDATE SET search_text = EXCLUDED.search_text
            WHERE EXCLUDED.search_text IS DISTINCT FROM cluster_search_docs.search_text;
            """,
            (cluster_id,),
        )
        return cur.rowcount > 0


def rebuild_empty_search_texts(
    conn: psycopg.Connection[Any],
    *,
    min_length: int = MIN_CONTENT_LENGTH,
    limit_clusters: int = 1000,
) -> SearchTextRebuildResult:
    """
    Rebuild search_text for clusters with empty or short search_text.

    Args:
        conn: Database connection
        min_length: Minimum length threshold (rebuild if shorter)
        limit_clusters: Maximum clusters to process

    Returns:
        SearchTextRebuildResult with counts
    """
    # Find clusters with empty/short search_text
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id
            FROM story_clusters c
            LEFT JOIN cluster_search_docs d ON d.cluster_id = c.id
            WHERE c.status = 'active'
              AND (d.search_text IS NULL OR LENGTH(d.search_text) < %s)
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (min_length, limit_clusters),
        )
        rows = cur.fetchall()

    cluster_ids = [UUID(str(_row_get(r, "id", 0))) for r in rows]
    scanned = 0
    rebuilt = 0

    for cid in cluster_ids:
        scanned += 1
        if rebuild_cluster_search_text(conn, cluster_id=cid):
            rebuilt += 1

    return SearchTextRebuildResult(clusters_scanned=scanned, clusters_rebuilt=rebuilt)


def is_content_sufficient(search_text: str | None, min_length: int = MIN_CONTENT_LENGTH) -> bool:
    """Check if content is sufficient for meaningful tagging."""
    if not search_text:
        return False
    return len(search_text.strip()) >= min_length


@dataclass(frozen=True)
class QuarantineResult:
    """Result of quarantining untaggable clusters."""

    clusters_scanned: int
    clusters_quarantined: int
    reasons: dict[str, int]  # reason -> count


def quarantine_untaggable_clusters(
    conn: psycopg.Connection[Any],
    *,
    min_content_length: int = MIN_CONTENT_LENGTH,
    limit_clusters: int = 500,
) -> QuarantineResult:
    """
    Quarantine clusters that cannot be meaningfully tagged.

    Criteria for quarantine:
    - No search_text or very short content (< min_content_length)
    - No items in the cluster
    - Placeholder titles (e.g., "arXiv cluster", "DOI cluster")

    Args:
        conn: Database connection
        min_content_length: Minimum content length
        limit_clusters: Maximum clusters to process

    Returns:
        QuarantineResult with counts and reasons
    """
    reasons: dict[str, int] = {}
    quarantined_ids: list[UUID] = []

    with conn.cursor() as cur:
        # Find clusters with insufficient content
        cur.execute(
            """
            SELECT
                c.id,
                c.canonical_title,
                d.search_text,
                (SELECT COUNT(*) FROM cluster_items ci WHERE ci.cluster_id = c.id) AS item_count
            FROM story_clusters c
            LEFT JOIN cluster_search_docs d ON d.cluster_id = c.id
            LEFT JOIN cluster_topics ct ON ct.cluster_id = c.id
            WHERE c.status = 'active'
              AND ct.cluster_id IS NULL  -- No topics assigned
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit_clusters,),
        )
        rows = cur.fetchall()

    placeholder_patterns = [
        "arxiv cluster",
        "doi cluster",
        "test cluster",
        "placeholder",
    ]

    for r in rows:
        cluster_id = UUID(str(_row_get(r, "id", 0)))
        title = str(_row_get(r, "canonical_title", 1) or "").lower()
        search_text = _row_get(r, "search_text", 2)
        item_count = int(_row_get(r, "item_count", 3) or 0)

        reason = None

        # Check for placeholder titles
        for pattern in placeholder_patterns:
            if pattern in title:
                reason = "placeholder_title"
                break

        # Check for no items
        if reason is None and item_count == 0:
            reason = "no_items"

        # Check for insufficient content
        if reason is None and not is_content_sufficient(search_text, min_content_length):
            reason = "insufficient_content"

        if reason:
            quarantined_ids.append(cluster_id)
            reasons[reason] = reasons.get(reason, 0) + 1

    # Quarantine identified clusters
    if quarantined_ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE story_clusters
                SET status = 'quarantined'
                WHERE id = ANY(%s::uuid[]);
                """,
                (quarantined_ids,),
            )

    return QuarantineResult(
        clusters_scanned=len(rows),
        clusters_quarantined=len(quarantined_ids),
        reasons=reasons,
    )


@dataclass(frozen=True)
class MaintenanceResult:
    """Result of running all maintenance tasks."""

    search_text_rebuilt: int
    clusters_tagged: int
    clusters_quarantined: int
    quarantine_reasons: dict[str, int]


def run_tagging_maintenance(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    min_content_length: int = MIN_CONTENT_LENGTH,
    limit_clusters: int = 500,
    max_topics_per_cluster: int = 3,
) -> MaintenanceResult:
    """
    Run all tagging maintenance tasks:
    1. Rebuild empty search_texts
    2. Re-tag clusters with rebuilt content
    3. Quarantine untaggable clusters

    Args:
        conn: Database connection
        now_utc: Current timestamp
        min_content_length: Minimum content length for tagging
        limit_clusters: Maximum clusters to process
        max_topics_per_cluster: Maximum topics per cluster

    Returns:
        MaintenanceResult with counts
    """
    now = now_utc or datetime.now(timezone.utc)

    # Step 1: Rebuild empty search_texts
    rebuild_result = rebuild_empty_search_texts(
        conn,
        min_length=min_content_length,
        limit_clusters=limit_clusters,
    )
    logger.info(
        "Rebuilt search_text for %d/%d clusters",
        rebuild_result.clusters_rebuilt,
        rebuild_result.clusters_scanned,
    )

    # Step 2: Re-tag untagged clusters (LLM classification)
    topics = _load_subtopics(conn) if has_subtopics(conn) else _load_topics(conn)

    tagged = 0
    if topics:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id
                FROM story_clusters c
                LEFT JOIN cluster_topics ct ON ct.cluster_id = c.id
                LEFT JOIN cluster_search_docs d ON d.cluster_id = c.id
                WHERE c.status = 'active'
                  AND ct.cluster_id IS NULL
                  AND d.search_text IS NOT NULL
                  AND LENGTH(d.search_text) >= %s
                ORDER BY c.updated_at DESC
                LIMIT %s;
                """,
                (min_content_length, limit_clusters),
            )
            rows = cur.fetchall()

        for r in rows:
            cid = UUID(str(_row_get(r, "id", 0)))
            if tag_cluster_topics(
                conn,
                cluster_id=cid,
                topics=topics,
                now_utc=now,
                max_topics=max_topics_per_cluster,
            ):
                tagged += 1

    logger.info("Tagged %d clusters", tagged)

    # Step 3: Quarantine untaggable clusters
    quarantine_result = quarantine_untaggable_clusters(
        conn,
        min_content_length=min_content_length,
        limit_clusters=limit_clusters,
    )
    logger.info(
        "Quarantined %d/%d clusters",
        quarantine_result.clusters_quarantined,
        quarantine_result.clusters_scanned,
    )

    return MaintenanceResult(
        search_text_rebuilt=rebuild_result.clusters_rebuilt,
        clusters_tagged=tagged,
        clusters_quarantined=quarantine_result.clusters_quarantined,
        quarantine_reasons=quarantine_result.reasons,
    )
