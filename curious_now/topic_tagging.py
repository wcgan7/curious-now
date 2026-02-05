from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class TopicSeed:
    name: str
    description_short: str | None
    aliases: list[str]
    parent_topic_id: UUID | None


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


def _normalize_text(text: str) -> str:
    s = text.lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def _contains_phrase(haystack_norm: str, phrase_norm: str) -> bool:
    if not phrase_norm:
        return False
    return f" {phrase_norm} " in haystack_norm


def load_topic_seed(path: Path | None = None) -> list[TopicSeed]:
    p = path or (_repo_root() / "config" / "topics.seed.v0.json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    topics = raw.get("topics")
    if not isinstance(topics, list):
        raise ValueError("topics.seed.v0.json must contain a top-level 'topics' array")

    out: list[TopicSeed] = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        aliases_raw = t.get("aliases")
        aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
        parent_topic_id = t.get("parent_topic_id")
        out.append(
            TopicSeed(
                name=" ".join(name.split()),
                description_short=(
                    " ".join(str(t.get("description_short")).split())
                    if isinstance(t.get("description_short"), str)
                    else None
                ),
                aliases=[a for a in (" ".join(x.split()) for x in aliases) if a],
                parent_topic_id=(
                    UUID(str(parent_topic_id)) if isinstance(parent_topic_id, str) else None
                ),
            )
        )
    return out


def seed_topics(
    conn: psycopg.Connection[Any],
    *,
    topics: list[TopicSeed],
    now_utc: datetime | None = None,
) -> int:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    inserted = 0
    with conn.cursor() as cur:
        for t in topics:
            cur.execute(
                """
                INSERT INTO topics(name, description_short, aliases, parent_topic_id, updated_at)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (name)
                DO UPDATE SET
                  description_short = EXCLUDED.description_short,
                  aliases = EXCLUDED.aliases,
                  parent_topic_id = EXCLUDED.parent_topic_id,
                  updated_at = EXCLUDED.updated_at
                RETURNING (xmax = 0) AS inserted;
                """,
                (t.name, t.description_short, Jsonb(t.aliases), t.parent_topic_id, now),
            )
            row = cur.fetchone()
            if row and bool(_row_get(row, "inserted", 0)):
                inserted += 1
    return inserted


def _load_topics(conn: psycopg.Connection[Any]) -> list[TopicDef]:
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


def _score_topic(
    *,
    topic: TopicDef,
    title_norm: str,
    text_norm: str,
) -> float:
    score = 0.0
    phrases = [topic.name, *topic.aliases]
    for p in phrases:
        pn = _normalize_text(p)
        if not pn:
            continue
        if _contains_phrase(title_norm, pn):
            score += 1.0 if p == topic.name else 0.8
        elif _contains_phrase(text_norm, pn):
            score += 0.6 if p == topic.name else 0.5
    return score


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


def tag_cluster_topics(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: UUID,
    topics: list[TopicDef],
    now_utc: datetime | None = None,
    max_topics: int = 3,
) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    cluster_text = _get_cluster_text(conn, cluster_id=cluster_id)
    if cluster_text is None:
        return False
    title, search_text = cluster_text

    title_norm = f" {_normalize_text(title)} "
    text_norm = f" {_normalize_text(search_text)} "

    scored: list[tuple[UUID, float]] = []
    for t in topics:
        s = _score_topic(topic=t, title_norm=title_norm, text_norm=text_norm)
        if s <= 0:
            continue
        scored.append((t.topic_id, s))
    scored.sort(key=lambda x: (-x[1], str(x[0])))
    selected = scored[: max(0, int(max_topics))]

    selected_ids = [tid for (tid, _) in selected]
    change_count = 0
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM cluster_topics
                WHERE cluster_id = %s
                  AND assignment_source = 'auto'
                  AND locked = false
                  AND NOT (topic_id = ANY(%s::uuid[]));
                """,
                (cluster_id, selected_ids),
            )
            change_count += int(cur.rowcount)

            for topic_id, score in selected:
                cur.execute(
                    """
                    INSERT INTO cluster_topics(
                      cluster_id, topic_id, score, assignment_source, locked
                    )
                    VALUES (%s,%s,%s,'auto',false)
                    ON CONFLICT (cluster_id, topic_id)
                    DO UPDATE SET
                      score = EXCLUDED.score
                    WHERE cluster_topics.assignment_source = 'auto'
                      AND cluster_topics.locked = false;
                    """,
                    (cluster_id, topic_id, float(score)),
                )
                change_count += int(cur.rowcount)

            if change_count > 0:
                cur.execute(
                    "UPDATE story_clusters SET updated_at = %s WHERE id = %s;",
                    (now, cluster_id),
                )

    return change_count > 0


def tag_recent_clusters(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    lookback_days: int = 14,
    limit_clusters: int = 500,
    max_topics_per_cluster: int = 3,
) -> TopicTaggingResult:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    since = now - timedelta(days=int(lookback_days))

    topics = _load_topics(conn)
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
    scanned = 0
    updated = 0
    for cid in cluster_ids:
        scanned += 1
        if tag_cluster_topics(
            conn,
            cluster_id=cid,
            topics=topics,
            now_utc=now,
            max_topics=max_topics_per_cluster,
        ):
            updated += 1

    return TopicTaggingResult(clusters_scanned=scanned, clusters_updated=updated)
