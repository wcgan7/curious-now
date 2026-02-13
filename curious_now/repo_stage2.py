from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors

from curious_now.api.schemas import (
    CategoryChip,
    ClusterCard,
    ClusterDetail,
    ClustersFeedResponse,
    ContentType,
    EvidenceItem,
    ItemSource,
    RedirectResponse,
    SearchResponse,
    Topic,
    TopicChip,
    TopicDetail,
    TopicsResponse,
)
from curious_now.repo_stage3 import glossary_entries_for_cluster

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)


def _normalize_pg_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, str):
        s = value.strip()
        # Common Postgres array text format: {a,b,c} or {}
        if s.startswith("{") and s.endswith("}"):
            inner = s[1:-1].strip()
            if not inner:
                return []
            # v0: content_type values are simple tokens (no commas/quotes expected)
            return [part for part in inner.split(",") if part]
    return [str(value)]


def _to_content_types(values: list[str]) -> list[ContentType]:
    out: list[ContentType] = []
    for v in values:
        try:
            out.append(ContentType(v))
        except ValueError:
            continue
    return out


def _normalize_json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def _extract_explainers(
    summary_intuition: Any,
    summary_deep_dive: Any,
) -> tuple[str | None, str | None, str | None]:
    """Return (eli5, eli20, deep_dive_markdown) from stored fields."""
    eli5 = str(summary_intuition) if summary_intuition else None
    eli20: str | None = None
    deep_dive_markdown: str | None = None

    if isinstance(summary_deep_dive, str):
        text = summary_deep_dive.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                deep_dive_markdown = summary_deep_dive
            else:
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("markdown"), str) and parsed["markdown"].strip():
                        deep_dive_markdown = parsed["markdown"]
                    if isinstance(parsed.get("eli20"), str) and parsed["eli20"].strip():
                        eli20 = parsed["eli20"]
                    if isinstance(parsed.get("eli5"), str) and parsed["eli5"].strip():
                        eli5 = parsed["eli5"]
        else:
            deep_dive_markdown = summary_deep_dive

    return eli5, eli20, deep_dive_markdown


def _load_cluster_topics(
    conn: psycopg.Connection[Any], cluster_ids: list[UUID]
) -> dict[UUID, list[TopicChip]]:
    if not cluster_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ct.cluster_id, t.id AS topic_id, t.name, ct.score
            FROM cluster_topics ct
            JOIN topics t ON t.id = ct.topic_id
            WHERE ct.cluster_id = ANY(%s)
            ORDER BY ct.cluster_id, ct.score DESC;
            """,
            (cluster_ids,),
        )
        rows = cur.fetchall()

    out: dict[UUID, list[TopicChip]] = defaultdict(list)
    for r in rows:
        out[r["cluster_id"]].append(
            TopicChip(topic_id=r["topic_id"], name=r["name"], score=float(r["score"]))
        )
    return out


def _load_cluster_categories(
    conn: psycopg.Connection[Any], cluster_ids: list[UUID]
) -> dict[UUID, list[CategoryChip]]:
    """Load categories derived from subtopic assignments."""
    if not cluster_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ct.cluster_id,
                cat.id AS category_id,
                cat.name AS category_name,
                MAX(ct.score) AS max_score
            FROM cluster_topics ct
            JOIN topics sub ON sub.id = ct.topic_id
            JOIN topics cat ON cat.id = sub.parent_topic_id
            WHERE ct.cluster_id = ANY(%s)
              AND sub.parent_topic_id IS NOT NULL
            GROUP BY ct.cluster_id, cat.id, cat.name
            ORDER BY ct.cluster_id, max_score DESC;
            """,
            (cluster_ids,),
        )
        rows = cur.fetchall()

    out: dict[UUID, list[CategoryChip]] = defaultdict(list)
    for r in rows:
        out[r["cluster_id"]].append(
            CategoryChip(
                category_id=r["category_id"],
                name=r["category_name"],
                score=float(r["max_score"]),
            )
        )
    return out


def _load_cluster_featured_images(
    conn: psycopg.Connection[Any], cluster_ids: list[UUID]
) -> dict[UUID, str]:
    """Load the first available image URL for each cluster."""
    if not cluster_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (ci.cluster_id)
              ci.cluster_id,
              i.image_url
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = ANY(%s)
              AND i.image_url IS NOT NULL
            ORDER BY ci.cluster_id, i.published_at DESC NULLS LAST, i.fetched_at DESC;
            """,
            (cluster_ids,),
        )
        rows = cur.fetchall()

    return {r["cluster_id"]: r["image_url"] for r in rows}


def _cluster_cards_from_rows(
    conn: psycopg.Connection[Any], rows: list[dict[str, Any]]
) -> list[ClusterCard]:
    cluster_ids = [r["cluster_id"] for r in rows]
    topics = _load_cluster_topics(conn, cluster_ids)
    categories = _load_cluster_categories(conn, cluster_ids)
    featured_images = _load_cluster_featured_images(conn, cluster_ids)
    cards: list[ClusterCard] = []
    for r in rows:
        content_type_badges = _to_content_types(_normalize_pg_array(r.get("content_type_badges")))
        cards.append(
            ClusterCard(
                cluster_id=r["cluster_id"],
                canonical_title=r["canonical_title"],
                updated_at=r["updated_at"],
                distinct_source_count=r["distinct_source_count"],
                top_topics=topics.get(r["cluster_id"], [])[:5],
                top_categories=categories.get(r["cluster_id"], [])[:3],
                content_type_badges=content_type_badges,
                method_badges=[str(x) for x in _normalize_json_array(r.get("method_badges"))],
                takeaway=r.get("takeaway"),
                anti_hype_flags=[str(x) for x in _normalize_json_array(r.get("anti_hype_flags"))],
                high_impact_label=bool(r.get("high_impact_label") or False),
                high_impact_reasons=[
                    str(x) for x in _normalize_json_array(r.get("high_impact_reasons"))
                ],
                featured_image_url=featured_images.get(r["cluster_id"]),
                deep_dive_skip_reason=r.get("deep_dive_skip_reason"),
            )
        )
    return cards


def _topic_match_clause_sql(topic_param: str = "%s") -> str:
    """Match a subtopic directly or a category through its immediate children."""
    return (
        "("
        f"ct.topic_id = {topic_param} "
        f"OR ct.topic_id IN (SELECT id FROM topics WHERE parent_topic_id = {topic_param})"
        ")"
    )


def get_feed(
    conn: psycopg.Connection[Any],
    *,
    tab: Literal["latest", "trending"],
    topic_id: UUID | None,
    content_type: str | None,
    page: int,
    page_size: int,
) -> ClustersFeedResponse:
    offset = (page - 1) * page_size
    where: list[str] = ["c.status = 'active'"]
    params: list[Any] = []

    if topic_id:
        where.append(
            "EXISTS (SELECT 1 FROM cluster_topics ct "
            f"WHERE ct.cluster_id = c.id AND {_topic_match_clause_sql()})"
        )
        params.extend([topic_id, topic_id])
    if content_type:
        where.append(
            "EXISTS (SELECT 1 FROM cluster_items ci "
            "JOIN items i ON i.id = ci.item_id "
            "WHERE ci.cluster_id = c.id AND i.content_type = %s)"
        )
        params.append(content_type)

    order_sql = (
        "c.updated_at DESC"
        if tab == "latest"
        else "c.high_impact_final_score DESC NULLS LAST, c.trending_score DESC, c.updated_at DESC"
    )
    where_sql = " AND ".join(where)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.method_badges,
              c.deep_dive_skip_reason,
              c.anti_hype_flags,
              c.high_impact_label,
              c.high_impact_reasons,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM story_clusters c
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s;
            """,
            (*params, page_size, offset),
        )
        rows = cur.fetchall()

    cards = _cluster_cards_from_rows(conn, rows)
    return ClustersFeedResponse(tab=tab, page=page, results=cards)


def _cluster_redirect(conn: psycopg.Connection[Any], cluster_id: UUID) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_cluster_id FROM cluster_redirects WHERE from_cluster_id = %s;",
            (cluster_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return cast(UUID, row["to_cluster_id"])


def cluster_redirect_to(conn: psycopg.Connection[Any], *, cluster_id: UUID) -> UUID | None:
    return _cluster_redirect(conn, cluster_id)


def get_cluster_updated_at(conn: psycopg.Connection[Any], *, cluster_id: UUID) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT updated_at FROM story_clusters WHERE id = %s;", (cluster_id,))
        row = cur.fetchone()
    if not row:
        return None
    return cast(datetime, row["updated_at"])


def get_topic_updated_at(conn: psycopg.Connection[Any], *, topic_id: UUID) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT updated_at FROM topics WHERE id = %s;", (topic_id,))
        row = cur.fetchone()
    if not row:
        return None
    return cast(datetime, row["updated_at"])


def get_cluster_detail_or_redirect(
    conn: psycopg.Connection[Any], *, cluster_id: UUID
) -> ClusterDetail | RedirectResponse:
    to_id = _cluster_redirect(conn, cluster_id)
    if to_id:
        return RedirectResponse(redirect_to_cluster_id=to_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              id AS cluster_id,
              canonical_title,
              created_at,
              updated_at,
              distinct_source_count,
              takeaway,
              summary_intuition,
              summary_deep_dive,
              assumptions,
              limitations,
              what_could_change_this,
              method_badges,
              anti_hype_flags,
              high_impact_label,
              high_impact_reasons,
              high_impact_final_score,
              high_impact_confidence,
              takeaway_supporting_item_ids,
              summary_intuition_supporting_item_ids,
              summary_deep_dive_supporting_item_ids,
              deep_dive_skip_reason
            FROM story_clusters
            WHERE id = %s;
            """,
            (cluster_id,),
        )
        cluster = cur.fetchone()
    if not cluster:
        raise KeyError("cluster not found")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              i.id AS item_id,
              i.title,
              i.url,
              i.published_at,
              i.content_type,
              i.image_url,
              s.id AS source_id,
              s.name AS source_name
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            JOIN sources s ON s.id = i.source_id
            WHERE ci.cluster_id = %s
            ORDER BY i.published_at DESC NULLS LAST, i.fetched_at DESC;
            """,
            (cluster_id,),
        )
        items = cur.fetchall()

    evidence: dict[str, list[EvidenceItem]] = defaultdict(list)
    breakdown: dict[str, int] = defaultdict(int)
    featured_image_url: str | None = None
    for r in items:
        ct = r["content_type"]
        breakdown[ct] += 1
        img_url = r.get("image_url")
        if featured_image_url is None and img_url:
            featured_image_url = img_url
        evidence[ct].append(
            EvidenceItem(
                item_id=r["item_id"],
                title=r["title"],
                url=r["url"],
                published_at=r["published_at"],
                content_type=ct,
                source=ItemSource(source_id=r["source_id"], name=r["source_name"]),
                image_url=img_url,
            )
        )

    topics = _load_cluster_topics(conn, [cluster_id]).get(cluster_id, [])
    categories = _load_cluster_categories(conn, [cluster_id]).get(cluster_id, [])
    glossary_entries = glossary_entries_for_cluster(conn, cluster_id=cluster_id)
    summary_intuition_eli5, summary_intuition_eli20, deep_dive_markdown = _extract_explainers(
        cluster.get("summary_intuition"),
        cluster.get("summary_deep_dive"),
    )
    return ClusterDetail(
        cluster_id=cluster["cluster_id"],
        canonical_title=cluster["canonical_title"],
        created_at=cluster["created_at"],
        updated_at=cluster["updated_at"],
        distinct_source_count=cluster["distinct_source_count"],
        topics=topics[:10],
        categories=categories,
        content_type_breakdown=dict(breakdown),
        evidence=dict(evidence),
        featured_image_url=featured_image_url,
        takeaway=cluster["takeaway"],
        summary_intuition=summary_intuition_eli5,
        summary_intuition_eli20=summary_intuition_eli20,
        summary_deep_dive=deep_dive_markdown,
        deep_dive_skip_reason=cluster.get("deep_dive_skip_reason"),
        assumptions=[str(x) for x in _normalize_json_array(cluster.get("assumptions"))],
        limitations=[str(x) for x in _normalize_json_array(cluster.get("limitations"))],
        what_could_change_this=[
            str(x) for x in _normalize_json_array(cluster.get("what_could_change_this"))
        ],
        method_badges=[str(x) for x in _normalize_json_array(cluster.get("method_badges"))],
        anti_hype_flags=[str(x) for x in _normalize_json_array(cluster.get("anti_hype_flags"))],
        high_impact_label=bool(cluster.get("high_impact_label") or False),
        high_impact_reasons=[
            str(x) for x in _normalize_json_array(cluster.get("high_impact_reasons"))
        ],
        high_impact_final_score=(
            float(cluster["high_impact_final_score"])
            if cluster.get("high_impact_final_score") is not None
            else None
        ),
        high_impact_confidence=(
            float(cluster["high_impact_confidence"])
            if cluster.get("high_impact_confidence") is not None
            else None
        ),
        takeaway_supporting_item_ids=list(_normalize_json_array(cluster.get("takeaway_supporting_item_ids"))),
        summary_intuition_supporting_item_ids=list(
            _normalize_json_array(cluster.get("summary_intuition_supporting_item_ids"))
        ),
        summary_deep_dive_supporting_item_ids=list(
            _normalize_json_array(cluster.get("summary_deep_dive_supporting_item_ids"))
        ),
        glossary_entries=glossary_entries,
    )


def list_topics(conn: psycopg.Connection[Any]) -> TopicsResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              id AS topic_id,
              name,
              description_short,
              parent_topic_id,
              CASE
                WHEN parent_topic_id IS NULL THEN 'category'
                ELSE 'subtopic'
              END AS topic_type
            FROM topics
            ORDER BY
              CASE WHEN parent_topic_id IS NULL THEN 0 ELSE 1 END,
              name ASC;
            """
        )
        rows = cur.fetchall()
    return TopicsResponse(
        topics=[
            Topic(
                topic_id=r["topic_id"],
                name=r["name"],
                description_short=r["description_short"],
                parent_topic_id=r["parent_topic_id"],
                topic_type=cast(Literal["category", "subtopic"], r["topic_type"]),
            )
            for r in rows
        ]
    )


def get_topic_detail(conn: psycopg.Connection[Any], *, topic_id: UUID) -> TopicDetail:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              id AS topic_id,
              name,
              description_short,
              parent_topic_id,
              CASE
                WHEN parent_topic_id IS NULL THEN 'category'
                ELSE 'subtopic'
              END AS topic_type
            FROM topics
            WHERE id = %s;
            """,
            (topic_id,),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("topic not found")

    topic = Topic(
        topic_id=row["topic_id"],
        name=row["name"],
        description_short=row["description_short"],
        parent_topic_id=row["parent_topic_id"],
        topic_type=cast(Literal["category", "subtopic"], row["topic_type"]),
    )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.method_badges,
              c.deep_dive_skip_reason,
              c.anti_hype_flags,
              c.high_impact_label,
              c.high_impact_reasons,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM story_clusters c
            JOIN cluster_topics ct ON ct.cluster_id = c.id
            WHERE {_topic_match_clause_sql()} AND c.status = 'active'
            ORDER BY c.updated_at DESC
            LIMIT 20;
            """,
            (topic_id, topic_id),
        )
        latest_rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT
              c.id AS cluster_id,
              c.canonical_title,
              c.updated_at,
              c.distinct_source_count,
              c.takeaway,
              c.method_badges,
              c.deep_dive_skip_reason,
              c.anti_hype_flags,
              c.high_impact_label,
              c.high_impact_reasons,
              (
                SELECT array_agg(DISTINCT i.content_type)
                FROM cluster_items ci
                JOIN items i ON i.id = ci.item_id
                WHERE ci.cluster_id = c.id
              ) AS content_type_badges
            FROM story_clusters c
            JOIN cluster_topics ct ON ct.cluster_id = c.id
            WHERE {_topic_match_clause_sql()} AND c.status = 'active'
            ORDER BY c.trending_score DESC, c.updated_at DESC
            LIMIT 20;
            """,
            (topic_id, topic_id),
        )
        trending_rows = cur.fetchall()

    return TopicDetail(
        topic=topic,
        latest_clusters=_cluster_cards_from_rows(conn, latest_rows),
        trending_clusters=_cluster_cards_from_rows(conn, trending_rows),
    )


def search(conn: psycopg.Connection[Any], *, query: str) -> SearchResponse:
    q = query.strip()

    base_select = """
        SELECT
          c.id AS cluster_id,
          c.canonical_title,
          c.updated_at,
          c.distinct_source_count,
          c.takeaway,
          c.method_badges,
          c.deep_dive_skip_reason,
          c.anti_hype_flags,
          c.high_impact_label,
          c.high_impact_reasons,
          (
            SELECT array_agg(DISTINCT i.content_type)
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = c.id
          ) AS content_type_badges
    """

    rows: list[dict[str, Any]] = []

    # Stage 9: identifier-first search.
    if _DOI_RE.match(q):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {base_select}
                FROM story_clusters c
                JOIN cluster_items ci ON ci.cluster_id = c.id
                JOIN items it ON it.id = ci.item_id
                WHERE it.doi = %s
                  AND c.status = 'active'
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT 50;
                """,
                (q,),
            )
            rows = cur.fetchall()
    elif _ARXIV_RE.match(q):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {base_select}
                FROM story_clusters c
                JOIN cluster_items ci ON ci.cluster_id = c.id
                JOIN items it ON it.id = ci.item_id
                WHERE it.arxiv_id = %s
                  AND c.status = 'active'
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT 50;
                """,
                (q,),
            )
            rows = cur.fetchall()

    # Stage 2 default: lexical search via cluster_search_docs (FTS).
    if not rows:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH q AS (
                  SELECT plainto_tsquery('english', %s) AS tsq
                )
                {base_select},
                  ts_rank_cd(d.search_tsv, q.tsq) AS rank
                FROM q
                JOIN cluster_search_docs d ON TRUE
                JOIN story_clusters c ON c.id = d.cluster_id
                WHERE d.search_tsv @@ q.tsq
                  AND c.status = 'active'
                ORDER BY rank DESC, c.updated_at DESC, c.id DESC
                LIMIT 50;
                """,
                (q,),
            )
            rows = cur.fetchall()

        # Stage 9 optional fallback: trigram similarity if FTS yields too few results.
        if len(rows) < 5 and q:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        {base_select},
                          similarity(d.search_text, %s) AS sim
                        FROM cluster_search_docs d
                        JOIN story_clusters c ON c.id = d.cluster_id
                        WHERE c.status = 'active'
                          AND d.search_text % %s
                        ORDER BY sim DESC, c.updated_at DESC, c.id DESC
                        LIMIT 50;
                        """,
                        (q, q),
                    )
                    rows = cur.fetchall()
            except (pg_errors.UndefinedFunction, psycopg.Error):
                # pg_trgm may be unavailable; keep FTS results.
                pass

    return SearchResponse(
        query=q, clusters=_cluster_cards_from_rows(conn, rows), topics=None, entities=None
    )
