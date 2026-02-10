"""AI content generation for story clusters.

This module provides functions to generate AI content (takeaways, embeddings,
intuition, deep-dives) for clusters stored in the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from curious_now.ai.deep_dive import (
    DeepDiveInput,
    DeepDiveResult,
    SourceSummary,
    deep_dive_to_json,
    generate_deep_dive,
)
from curious_now.ai.embeddings import (
    ClusterEmbeddingInput,
    EmbeddingResult,
    generate_cluster_embedding,
    get_embedding_provider,
)
from curious_now.ai.intuition import (
    IntuitionInput,
    IntuitionResult,
    generate_intuition,
    generate_intuition_from_abstracts,
    generate_news_summary,
    NEWS_SUMMARY_MIN_CONTENT_CHARS,
)
from curious_now.ai.llm_adapter import LLMAdapter, get_llm_adapter
from curious_now.ai.takeaways import (
    ItemSummary,
    TakeawayInput,
    TakeawayResult,
    generate_takeaway,
)
from curious_now.paper_text_hydration import hydrate_paper_text

logger = logging.getLogger(__name__)
_PAPER_CONTENT_TYPES = {"preprint", "peer_reviewed"}
_ABSTRACT_TEXT_SOURCES = {"arxiv_api", "crossref", "openalex"}
_FULLTEXT_TEXT_SOURCES = {
    "landing_page",
    "arxiv_pdf",
    "arxiv_html",
    "arxiv_eprint",
    "unpaywall_pdf",
    "unpaywall_landing",
    "openalex_pdf",
    "openalex_landing",
    "crossref_pdf",
    "crossref_landing",
    "pmc_oa",
    "publisher_pdf",
}
_DEEP_DIVE_SKIP_REASON_NO_FULLTEXT = "no_fulltext"
_DEEP_DIVE_SKIP_REASON_ABSTRACT_ONLY = "abstract_only"
_DEEP_DIVE_SKIP_REASON_GEN_FAILED = "generation_failed"


@dataclass
class GenerateTakeawaysResult:
    """Result of takeaway generation batch."""

    clusters_processed: int
    clusters_succeeded: int
    clusters_failed: int


@dataclass
class GenerateEmbeddingsResult:
    """Result of embedding generation batch."""

    clusters_processed: int
    clusters_succeeded: int
    clusters_failed: int
    clusters_skipped: int  # Already had up-to-date embeddings


@dataclass
class GenerateIntuitionResult:
    """Result of intuition generation batch."""

    clusters_processed: int
    clusters_succeeded: int
    clusters_failed: int
    clusters_skipped: int


@dataclass
class GenerateDeepDivesResult:
    """Result of deep dive generation batch."""

    clusters_processed: int
    clusters_succeeded: int
    clusters_failed: int
    clusters_skipped: int  # Skipped because not a paper


def _get_clusters_needing_takeaways(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get clusters that need takeaway generation."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.distinct_source_count
            FROM story_clusters c
            WHERE c.status = 'active'
              AND c.takeaway IS NULL
              AND c.distinct_source_count >= 1
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()


def _get_cluster_items_for_takeaway(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> list[dict[str, Any]]:
    """Get items for a cluster to use in takeaway generation."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                i.id AS item_id,
                i.title,
                i.snippet,
                i.full_text,
                i.full_text_status,
                i.full_text_source,
                i.full_text_kind,
                i.full_text_license,
                s.name AS source_name,
                i.content_type AS source_type,
                i.published_at
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            JOIN sources s ON s.id = i.source_id
            WHERE ci.cluster_id = %s
            ORDER BY ci.role ASC, i.published_at DESC NULLS LAST
            LIMIT 10;
            """,
            (cluster_id,),
        )
        return cur.fetchall()


def _paper_text_kind(item: dict[str, Any]) -> str:
    """Classify hydrated paper text quality for generation gates."""
    text = item.get("full_text")
    if not (text and str(text).strip()):
        return "missing"
    kind = str(item.get("full_text_kind") or "").strip().lower()
    if kind in {"fulltext", "abstract"}:
        return kind
    source = str(item.get("full_text_source") or "").strip().lower()
    if source in _FULLTEXT_TEXT_SOURCES:
        return "fulltext"
    if source in _ABSTRACT_TEXT_SOURCES:
        return "abstract"
    # Safety default: unknown provenance is treated as abstract-grade.
    return "abstract"


def _build_abstract_context(items: list[dict[str, Any]], *, max_sources: int = 5) -> str | None:
    """Build compact abstract-only context for ELI5 fallback generation."""
    parts: list[str] = []
    for item in items[:max_sources]:
        text = item.get("full_text")
        if not (text and str(text).strip()):
            continue
        title = str(item.get("title") or "Untitled source").strip()
        source_name = str(item.get("source_name") or "").strip()
        header = f"- {title}"
        if source_name:
            header += f" [{source_name}]"
        parts.append(f"{header}\n{text}")
    if not parts:
        return None
    return "\n\n".join(parts)


def _split_paper_items_by_text_quality(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split paper items into fulltext-backed and abstract-backed subsets."""
    fulltext_items: list[dict[str, Any]] = []
    abstract_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("source_type") not in _PAPER_CONTENT_TYPES:
            continue
        kind = _paper_text_kind(item)
        if kind == "fulltext":
            fulltext_items.append(item)
        elif kind == "abstract":
            abstract_items.append(item)
    return fulltext_items, abstract_items


def _ensure_paper_text_hydrated(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure paper sources have hydrated text before explainer generation."""
    missing_ids = [
        item["item_id"]
        for item in items
        if item.get("source_type") in _PAPER_CONTENT_TYPES
        and not (item.get("full_text") and str(item.get("full_text")).strip())
    ]
    if not missing_ids:
        return items

    hydrate_paper_text(conn, limit=len(missing_ids), item_ids=missing_ids)
    reloaded = _get_cluster_items_for_takeaway(conn, cluster_id)
    return reloaded


def _get_cluster_topics(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> list[str]:
    """Get topic names for a cluster."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT t.name
            FROM cluster_topics ct
            JOIN topics t ON t.id = ct.topic_id
            WHERE ct.cluster_id = %s
            ORDER BY ct.score DESC
            LIMIT 5;
            """,
            (cluster_id,),
        )
        return [row["name"] for row in cur.fetchall()]


def _update_cluster_takeaway(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    takeaway: str,
    item_ids: list[UUID],
) -> None:
    """Update cluster with generated takeaway."""
    # Convert UUIDs to JSON array of strings for JSONB column
    item_ids_json = json.dumps([str(uid) for uid in item_ids])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE story_clusters
            SET takeaway = %s,
                takeaway_supporting_item_ids = %s::jsonb,
                updated_at = now()
            WHERE id = %s;
            """,
            (takeaway, item_ids_json, cluster_id),
        )


def generate_takeaways_for_clusters(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    adapter: LLMAdapter | None = None,
) -> GenerateTakeawaysResult:
    """
    Generate takeaways for clusters that don't have them.

    Args:
        conn: Database connection
        limit: Maximum number of clusters to process
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        GenerateTakeawaysResult with processing statistics
    """
    if adapter is None:
        adapter = get_llm_adapter()

    clusters = _get_clusters_needing_takeaways(conn, limit=limit)
    processed = 0
    succeeded = 0
    failed = 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        canonical_title = cluster["canonical_title"]
        processed += 1

        try:
            # Get items for this cluster
            items = _get_cluster_items_for_takeaway(conn, cluster_id)
            if not items:
                logger.warning("No items found for cluster %s", cluster_id)
                failed += 1
                continue

            # Get topics
            topics = _get_cluster_topics(conn, cluster_id)

            # Build input and track item IDs
            item_summaries = []
            item_ids = []
            for item in items:
                item_summaries.append(
                    ItemSummary(
                        title=item["title"],
                        snippet=item.get("snippet"),
                        source_name=item.get("source_name"),
                        source_type=item.get("source_type"),
                        published_at=(
                            str(item["published_at"]) if item.get("published_at") else None
                        ),
                    )
                )
                item_ids.append(item["item_id"])

            input_data = TakeawayInput(
                cluster_title=canonical_title,
                items=item_summaries,
                topic_names=topics if topics else None,
            )

            # Generate takeaway
            result: TakeawayResult = generate_takeaway(input_data, adapter=adapter)

            if not result.success:
                logger.warning(
                    "Takeaway generation failed for cluster %s: %s",
                    cluster_id,
                    result.error,
                )
                failed += 1
                continue

            # Update cluster with supporting item IDs
            _update_cluster_takeaway(conn, cluster_id, result.takeaway, item_ids)
            succeeded += 1
            logger.info(
                "Generated takeaway for cluster %s (confidence: %.2f)",
                cluster_id,
                result.confidence,
            )

        except Exception as e:
            logger.exception("Error generating takeaway for cluster %s: %s", cluster_id, e)
            failed += 1

    return GenerateTakeawaysResult(
        clusters_processed=processed,
        clusters_succeeded=succeeded,
        clusters_failed=failed,
    )


def _get_clusters_needing_embeddings(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Get clusters that need embedding generation."""
    if force:
        # Get all active clusters
        query = """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway
            FROM story_clusters c
            WHERE c.status = 'active'
            ORDER BY c.updated_at DESC
            LIMIT %s;
        """
    else:
        # Get clusters without embeddings
        query = """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway
            FROM story_clusters c
            LEFT JOIN cluster_embeddings ce ON ce.cluster_id = c.id
            WHERE c.status = 'active'
              AND ce.cluster_id IS NULL
            ORDER BY c.updated_at DESC
            LIMIT %s;
        """

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


def _compute_source_text_hash(text: str) -> str:
    """Compute hash of source text for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _parse_deep_dive_text(summary_deep_dive_text: Any) -> dict[str, Any]:
    """Parse stored deep-dive text payload if it is JSON-like."""
    if not summary_deep_dive_text:
        return {}
    if isinstance(summary_deep_dive_text, dict):
        return summary_deep_dive_text
    if isinstance(summary_deep_dive_text, str):
        text = summary_deep_dive_text.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
    return {}


def _get_deep_dive_markdown(summary_deep_dive_text: Any) -> str | None:
    """Extract markdown from stored deep-dive text."""
    payload = _parse_deep_dive_text(summary_deep_dive_text)
    markdown = payload.get("markdown")
    if isinstance(markdown, str) and markdown.strip():
        return markdown
    if isinstance(summary_deep_dive_text, str) and summary_deep_dive_text.strip():
        return summary_deep_dive_text
    return None


def _merge_explainers_into_deep_dive(
    *,
    summary_deep_dive_text: Any,
    deep_dive_markdown: str,
    source_count: int,
    eli20: str | None,
    eli5: str | None,
) -> dict[str, Any]:
    """Build canonical deep-dive payload with optional intuition layers."""
    existing = _parse_deep_dive_text(summary_deep_dive_text)
    payload: dict[str, Any] = {
        "markdown": deep_dive_markdown,
        "generated_at": existing.get("generated_at", ""),
        "source_count": int(existing.get("source_count", source_count) or source_count),
    }
    if eli20:
        payload["eli20"] = eli20
    elif isinstance(existing.get("eli20"), str):
        payload["eli20"] = existing["eli20"]
    if eli5:
        payload["eli5"] = eli5
    elif isinstance(existing.get("eli5"), str):
        payload["eli5"] = existing["eli5"]
    return payload


def _upsert_cluster_embedding(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    embedding: list[float],
    model: str,
    source_text_hash: str,
) -> None:
    """Insert or update cluster embedding."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO cluster_embeddings
                (cluster_id, embedding, embedding_model, source_text_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cluster_id) DO UPDATE
            SET embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                source_text_hash = EXCLUDED.source_text_hash,
                updated_at = now();
            """,
            (cluster_id, embedding, model, source_text_hash),
        )


def _get_existing_embedding_hash(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> str | None:
    """Get existing embedding source text hash if it exists."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT source_text_hash FROM cluster_embeddings WHERE cluster_id = %s;",
            (cluster_id,),
        )
        row = cur.fetchone()
    return row["source_text_hash"] if row else None


def generate_embeddings_for_clusters(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    force: bool = False,
    provider_name: str | None = None,
) -> GenerateEmbeddingsResult:
    """
    Generate embeddings for clusters that don't have them.

    Args:
        conn: Database connection
        limit: Maximum number of clusters to process
        force: If True, regenerate embeddings for all clusters
        provider_name: Embedding provider to use (defaults to configured provider)

    Returns:
        GenerateEmbeddingsResult with processing statistics
    """
    provider = get_embedding_provider(provider_name)

    clusters = _get_clusters_needing_embeddings(conn, limit=limit, force=force)
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        canonical_title = cluster["canonical_title"]
        takeaway = cluster.get("takeaway") or ""
        processed += 1

        try:
            # Get topics for richer embedding
            topics = _get_cluster_topics(conn, cluster_id)

            # Build text for embedding
            text_parts = [canonical_title]
            if takeaway:
                text_parts.append(takeaway)
            if topics:
                text_parts.append("Topics: " + ", ".join(topics))

            source_text = " | ".join(text_parts)
            source_hash = _compute_source_text_hash(source_text)

            # Check if we can skip (same source text)
            if not force:
                existing_hash = _get_existing_embedding_hash(conn, cluster_id)
                if existing_hash == source_hash:
                    skipped += 1
                    continue

            # Generate embedding
            embedding_input = ClusterEmbeddingInput(
                cluster_id=str(cluster_id),
                canonical_title=canonical_title,
                takeaway=takeaway,
                topic_names=topics if topics else None,
            )
            result: EmbeddingResult = generate_cluster_embedding(
                embedding_input,
                provider=provider,
            )

            if not result.success:
                logger.warning(
                    "Embedding generation failed for cluster %s: %s",
                    cluster_id,
                    result.error,
                )
                failed += 1
                continue

            # Store embedding
            _upsert_cluster_embedding(
                conn,
                cluster_id,
                result.embedding,
                result.model,
                source_hash,
            )
            succeeded += 1
            logger.info("Generated embedding for cluster %s", cluster_id)

        except Exception as e:
            logger.exception("Error generating embedding for cluster %s: %s", cluster_id, e)
            failed += 1

    return GenerateEmbeddingsResult(
        clusters_processed=processed,
        clusters_succeeded=succeeded,
        clusters_failed=failed,
        clusters_skipped=skipped,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 Enrichment (intuition, deep-dive, confidence, flags, badges)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GenerateStage3Result:
    """Result of Stage 3 enrichment batch."""

    clusters_processed: int
    clusters_succeeded: int
    clusters_failed: int
    clusters_skipped: int  # Already had all Stage 3 fields


def _get_clusters_needing_stage3(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get clusters that need Stage 3 enrichment (missing intuition or deep-dive)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                c.distinct_source_count,
                c.summary_deep_dive
            FROM story_clusters c
            WHERE c.status = 'active'
              AND c.takeaway IS NOT NULL
              AND (c.summary_intuition IS NULL OR c.summary_deep_dive IS NULL)
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()


def _get_clusters_needing_intuition(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get clusters that need intuition (have takeaway but no intuition)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                c.distinct_source_count,
                c.summary_deep_dive
            FROM story_clusters c
            WHERE c.status = 'active'
              AND c.takeaway IS NOT NULL
              AND c.summary_intuition IS NULL
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()


def _get_clusters_needing_deep_dive(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Get clusters that need deep dives.

    Only returns clusters where items are papers (preprint or peer_reviewed),
    since articles/press releases don't need deep dives.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                c.distinct_source_count,
                c.updated_at
            FROM story_clusters c
            JOIN cluster_items ci ON c.id = ci.cluster_id
            JOIN items i ON ci.item_id = i.id
            WHERE c.status = 'active'
              AND c.takeaway IS NOT NULL
              AND c.summary_deep_dive IS NULL
              AND i.content_type IN ('preprint', 'peer_reviewed')
            ORDER BY c.updated_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()


def _get_cluster_content_types(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> list[str]:
    """Get distinct content types for items in a cluster."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT i.content_type
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = %s
              AND i.content_type IS NOT NULL;
            """,
            (cluster_id,),
        )
        return [row["content_type"] for row in cur.fetchall()]


def _compute_anti_hype_flags(
    content_types: list[str],
    source_count: int,
) -> list[str]:
    """
    Compute anti-hype flags based on evidence types.

    Returns list of flag strings.
    """
    flags = []

    has_peer_reviewed = "peer_reviewed" in content_types
    has_preprint = "preprint" in content_types
    has_press_release = "press_release" in content_types

    # Preprint not yet peer-reviewed
    if has_preprint and not has_peer_reviewed:
        flags.append("preprint_not_peer_reviewed")

    # Press release only (no primary evidence)
    if has_press_release and not has_preprint and not has_peer_reviewed:
        flags.append("press_release_only")

    # Single source
    if source_count == 1:
        flags.append("single_source")

    return flags


def _compute_method_badges(content_types: list[str]) -> list[str]:
    """
    Compute method badges based on content types.

    Note: v0 just assigns based on content type. Future versions
    could use LLM to extract methods from text.
    """
    badges = []

    if "peer_reviewed" in content_types or "preprint" in content_types:
        # Assume research involves some form of study
        badges.append("observational")

    if "report" in content_types:
        badges.append("benchmark")

    return badges


def _update_cluster_stage3(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    *,
    summary_intuition: str | None = None,
    summary_intuition_item_ids: list[UUID] | None = None,
    summary_deep_dive: dict[str, Any] | None = None,
    summary_deep_dive_item_ids: list[UUID] | None = None,
    anti_hype_flags: list[str] | None = None,
    method_badges: list[str] | None = None,
    limitations: list[str] | None = None,
) -> None:
    """Update cluster with Stage 3 enrichment fields."""
    import json

    updates = []
    params: list[Any] = []

    if summary_intuition is not None:
        updates.append("summary_intuition = %s")
        params.append(summary_intuition)
        updates.append("summary_intuition_supporting_item_ids = %s")
        params.append(json.dumps([str(i) for i in (summary_intuition_item_ids or [])]))

    if summary_deep_dive is not None:
        updates.append("summary_deep_dive = %s")
        params.append(json.dumps(summary_deep_dive))
        updates.append("summary_deep_dive_supporting_item_ids = %s")
        params.append(json.dumps([str(i) for i in (summary_deep_dive_item_ids or [])]))

    if anti_hype_flags is not None:
        updates.append("anti_hype_flags = %s")
        params.append(json.dumps(anti_hype_flags))

    if method_badges is not None:
        updates.append("method_badges = %s")
        params.append(json.dumps(method_badges))

    if limitations is not None:
        updates.append("limitations = %s")
        params.append(json.dumps(limitations))

    if not updates:
        return

    updates.append("updated_at = now()")
    params.append(cluster_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE story_clusters
            SET {', '.join(updates)}
            WHERE id = %s;
            """,
            tuple(params),
        )


def _set_deep_dive_skip_reason(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    reason: str | None,
) -> None:
    """Persist explainable reason for why deep-dive is absent."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE story_clusters
                SET deep_dive_skip_reason = %s
                WHERE id = %s;
                """,
                (reason, cluster_id),
            )
    except psycopg.errors.UndefinedColumn:
        # Compatibility during rolling deploys before migration is applied.
        return


def enrich_stage3_for_clusters(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    adapter: LLMAdapter | None = None,
) -> GenerateStage3Result:
    """
    Generate Stage 3 enrichment (intuition, deep-dive, confidence, flags) for clusters.

    Requires clusters to already have takeaways generated.

    Args:
        conn: Database connection
        limit: Maximum number of clusters to process
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        GenerateStage3Result with processing statistics
    """
    if adapter is None:
        adapter = get_llm_adapter()

    clusters = _get_clusters_needing_stage3(conn, limit=limit)
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        canonical_title = cluster["canonical_title"]
        takeaway = cluster.get("takeaway")
        source_count = cluster.get("distinct_source_count", 1)
        processed += 1

        if not takeaway:
            logger.warning("Cluster %s has no takeaway, skipping Stage 3", cluster_id)
            skipped += 1
            continue

        try:
            # Get items for supporting IDs
            items = _get_cluster_items_for_takeaway(conn, cluster_id)
            item_ids = [item["item_id"] for item in items]

            # Get content types for heuristics
            content_types = _get_cluster_content_types(conn, cluster_id)
            has_paper_sources = any(ct in _PAPER_CONTENT_TYPES for ct in content_types)

            # ─────────────────────────────────────────────────────────────
            # Generate deep-dive
            # ─────────────────────────────────────────────────────────────
            deep_dive_markdown = _get_deep_dive_markdown(cluster.get("summary_deep_dive"))
            summary_deep_dive: dict[str, Any] | None = None
            abstract_fallback_intuition: str | None = None
            abstract_fallback_item_ids: list[UUID] | None = None
            if not deep_dive_markdown:
                if has_paper_sources:
                    items = _ensure_paper_text_hydrated(conn, cluster_id, items)
                    fulltext_items, abstract_items = _split_paper_items_by_text_quality(items)
                    if not fulltext_items:
                        abstract_context = _build_abstract_context(abstract_items)
                        if abstract_context:
                            _set_deep_dive_skip_reason(
                                conn,
                                cluster_id,
                                _DEEP_DIVE_SKIP_REASON_ABSTRACT_ONLY,
                            )
                            abstract_result = generate_intuition_from_abstracts(
                                cluster_title=canonical_title,
                                abstracts_text=abstract_context,
                                adapter=adapter,
                            )
                            if abstract_result.success and abstract_result.eli5:
                                abstract_fallback_intuition = abstract_result.eli5
                                abstract_fallback_item_ids = [
                                    item["item_id"] for item in abstract_items
                                ]
                        logger.info(
                            "Cluster %s: skipped deep-dive (no full text paper sources)",
                            cluster_id,
                        )
                        if not abstract_context:
                            _set_deep_dive_skip_reason(
                                conn,
                                cluster_id,
                                _DEEP_DIVE_SKIP_REASON_NO_FULLTEXT,
                            )
                    else:
                        source_summaries = [
                            SourceSummary(
                                title=item["title"],
                                snippet=item.get("snippet"),
                                source_name=item.get("source_name"),
                                source_type=item.get("source_type"),
                                full_text=item.get("full_text"),
                            )
                            for item in fulltext_items
                        ]
                        deep_dive_input = DeepDiveInput(
                            cluster_title=canonical_title,
                            source_summaries=source_summaries,
                        )
                        deep_dive_result: DeepDiveResult = generate_deep_dive(
                            deep_dive_input, adapter=adapter
                        )
                        if deep_dive_result.success and deep_dive_result.content:
                            deep_dive_markdown = deep_dive_result.content.markdown
                            summary_deep_dive = deep_dive_to_json(deep_dive_result.content)
                            _set_deep_dive_skip_reason(conn, cluster_id, None)
                        else:
                            logger.warning(
                                "Deep-dive generation failed for cluster %s: %s",
                                cluster_id,
                                deep_dive_result.error,
                            )
                            _set_deep_dive_skip_reason(
                                conn,
                                cluster_id,
                                _DEEP_DIVE_SKIP_REASON_GEN_FAILED,
                            )
                else:
                    source_summaries = [
                        SourceSummary(
                            title=item["title"],
                            snippet=item.get("snippet"),
                            source_name=item.get("source_name"),
                            source_type=item.get("source_type"),
                            full_text=item.get("full_text"),
                        )
                        for item in items
                    ]
                    deep_dive_input = DeepDiveInput(
                        cluster_title=canonical_title,
                        source_summaries=source_summaries,
                    )
                    deep_dive_result = generate_deep_dive(deep_dive_input, adapter=adapter)
                    if deep_dive_result.success and deep_dive_result.content:
                        deep_dive_markdown = deep_dive_result.content.markdown
                        summary_deep_dive = deep_dive_to_json(deep_dive_result.content)
                        _set_deep_dive_skip_reason(conn, cluster_id, None)
                    else:
                        logger.warning(
                            "Deep-dive generation failed for cluster %s: %s",
                            cluster_id,
                            deep_dive_result.error,
                        )
                        _set_deep_dive_skip_reason(
                            conn,
                            cluster_id,
                            _DEEP_DIVE_SKIP_REASON_GEN_FAILED,
                        )

            if abstract_fallback_intuition and not deep_dive_markdown:
                summary_intuition = abstract_fallback_intuition
                _update_cluster_stage3(
                    conn,
                    cluster_id,
                    summary_intuition=summary_intuition,
                    summary_intuition_item_ids=abstract_fallback_item_ids or item_ids,
                )
                succeeded += 1
                continue

            # ─────────────────────────────────────────────────────────────
            # Generate layered intuition: Deep Dive -> ELI20 -> ELI5
            # ─────────────────────────────────────────────────────────────
            summary_intuition = None
            intuition_result: IntuitionResult | None = None
            if deep_dive_markdown:
                intuition_input = IntuitionInput(
                    cluster_title=canonical_title,
                    deep_dive_markdown=deep_dive_markdown,
                )
                intuition_result = generate_intuition(intuition_input, adapter=adapter)
                if intuition_result.success:
                    summary_intuition = intuition_result.eli5
                    summary_deep_dive = _merge_explainers_into_deep_dive(
                        summary_deep_dive_text=(
                            summary_deep_dive or cluster.get("summary_deep_dive")
                        ),
                        deep_dive_markdown=deep_dive_markdown,
                        source_count=len(items),
                        eli20=intuition_result.eli20,
                        eli5=intuition_result.eli5,
                    )
                    logger.info(
                        "Cluster %s intuition generated: eli20_words=%s eli5_words=%s "
                        "eli20_rerun=%s eli5_rerun=%s eli20_digit_flag=%s eli5_digit_flag=%s",
                        cluster_id,
                        intuition_result.eli20_word_count,
                        intuition_result.eli5_word_count,
                        intuition_result.eli20_rerun_shorten,
                        intuition_result.eli5_rerun_shorten,
                        intuition_result.eli20_new_digit_flag,
                        intuition_result.eli5_new_digit_flag,
                    )
                else:
                    logger.warning(
                        "Intuition generation failed for cluster %s: %s",
                        cluster_id,
                        intuition_result.error,
                    )

            # ─────────────────────────────────────────────────────────────
            # Compute heuristics
            # ─────────────────────────────────────────────────────────────
            anti_hype_flags = _compute_anti_hype_flags(content_types, source_count)
            method_badges = _compute_method_badges(content_types)

            # ─────────────────────────────────────────────────────────────
            # Update cluster
            # ─────────────────────────────────────────────────────────────
            _update_cluster_stage3(
                conn,
                cluster_id,
                summary_intuition=summary_intuition,
                summary_intuition_item_ids=item_ids if summary_intuition else None,
                summary_deep_dive=summary_deep_dive,
                summary_deep_dive_item_ids=item_ids if summary_deep_dive else None,
                anti_hype_flags=anti_hype_flags,
                method_badges=method_badges,
            )

            succeeded += 1
            logger.info(
                "Stage 3 enrichment complete for cluster %s "
                "(intuition: %s, deep-dive: %s)",
                cluster_id,
                "yes" if summary_intuition else "no",
                "yes" if summary_deep_dive else "no",
            )

        except Exception as e:
            logger.exception(
                "Error in Stage 3 enrichment for cluster %s: %s", cluster_id, e
            )
            failed += 1

    return GenerateStage3Result(
        clusters_processed=processed,
        clusters_succeeded=succeeded,
        clusters_failed=failed,
        clusters_skipped=skipped,
    )


def generate_intuition_for_clusters(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    adapter: LLMAdapter | None = None,
) -> GenerateIntuitionResult:
    """
    Generate layered intuition for clusters that have takeaways but no intuition.

    Cascade:
    - Deep Dive (existing or freshly generated) -> ELI20
    - ELI20 -> ELI5

    Args:
        conn: Database connection
        limit: Maximum number of clusters to process
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        GenerateIntuitionResult with processing statistics
    """
    if adapter is None:
        adapter = get_llm_adapter()

    clusters = _get_clusters_needing_intuition(conn, limit=limit)
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        canonical_title = cluster["canonical_title"]
        takeaway = cluster.get("takeaway")
        processed += 1

        if not takeaway:
            logger.warning("Cluster %s has no takeaway, skipping intuition", cluster_id)
            skipped += 1
            continue

        try:
            items = _get_cluster_items_for_takeaway(conn, cluster_id)
            item_ids = [item["item_id"] for item in items]
            content_types = _get_cluster_content_types(conn, cluster_id)
            source_count = cluster.get("distinct_source_count", 1)
            summary_deep_dive_text = cluster.get("summary_deep_dive")
            deep_dive_markdown = _get_deep_dive_markdown(summary_deep_dive_text)

            if not deep_dive_markdown:
                has_paper_sources = any(ct in _PAPER_CONTENT_TYPES for ct in content_types)
                if has_paper_sources:
                    items = _ensure_paper_text_hydrated(conn, cluster_id, items)
                    fulltext_items, abstract_items = _split_paper_items_by_text_quality(items)
                    if not fulltext_items:
                        abstract_context = _build_abstract_context(abstract_items)
                        if not abstract_context:
                            skipped += 1
                            _set_deep_dive_skip_reason(
                                conn,
                                cluster_id,
                                _DEEP_DIVE_SKIP_REASON_NO_FULLTEXT,
                            )
                            logger.info(
                                "Cluster %s skipped intuition: no deep-dive full text or abstracts",
                                cluster_id,
                            )
                            continue
                        _set_deep_dive_skip_reason(
                            conn,
                            cluster_id,
                            _DEEP_DIVE_SKIP_REASON_ABSTRACT_ONLY,
                        )
                        abstract_result = generate_intuition_from_abstracts(
                            cluster_title=canonical_title,
                            abstracts_text=abstract_context,
                            adapter=adapter,
                        )
                        if not abstract_result.success:
                            failed += 1
                            logger.warning(
                                "Abstract-only intuition generation failed for cluster %s: %s",
                                cluster_id,
                                abstract_result.error,
                            )
                            continue
                        anti_hype_flags = _compute_anti_hype_flags(content_types, source_count)
                        method_badges = _compute_method_badges(content_types)
                        _update_cluster_stage3(
                            conn,
                            cluster_id,
                            summary_intuition=abstract_result.eli5,
                            summary_intuition_item_ids=[
                                item["item_id"] for item in abstract_items
                            ],
                            anti_hype_flags=anti_hype_flags,
                            method_badges=method_badges,
                        )
                        succeeded += 1
                        logger.info(
                            "Intuition generated from abstracts for cluster %s (eli5_words=%s)",
                            cluster_id,
                            abstract_result.eli5_word_count,
                        )
                        continue
                    source_summaries = [
                        SourceSummary(
                            title=item["title"],
                            snippet=item.get("snippet"),
                            source_name=item.get("source_name"),
                            source_type=item.get("source_type"),
                            full_text=item.get("full_text"),
                        )
                        for item in fulltext_items
                    ]
                    # Generate deep dive only for paper sources with full text
                    deep_dive_input = DeepDiveInput(
                        cluster_title=canonical_title,
                        source_summaries=source_summaries,
                    )
                    deep_dive_result = generate_deep_dive(deep_dive_input, adapter=adapter)
                    if deep_dive_result.success and deep_dive_result.content:
                        deep_dive_markdown = deep_dive_result.content.markdown
                        summary_deep_dive_text = deep_dive_to_json(deep_dive_result.content)
                        _set_deep_dive_skip_reason(conn, cluster_id, None)
                    else:
                        logger.warning(
                            "Deep-dive generation failed for cluster %s before intuition: %s",
                            cluster_id,
                            deep_dive_result.error,
                        )
                        _set_deep_dive_skip_reason(
                            conn,
                            cluster_id,
                            _DEEP_DIVE_SKIP_REASON_GEN_FAILED,
                        )
                        failed += 1
                        continue
                else:
                    # Non-paper sources (news, journalism, etc.): use simple news summary
                    # No deep dive for these - the article itself is the explanation
                    if not items:
                        skipped += 1
                        logger.info(
                            "Cluster %s skipped: no items for news summary",
                            cluster_id,
                        )
                        continue

                    # Use first item's content for news summary (prefer full_text over snippet)
                    first_item = items[0]
                    news_result = generate_news_summary(
                        title=first_item.get("title", canonical_title),
                        snippet=first_item.get("snippet"),
                        full_text=first_item.get("full_text"),
                        adapter=adapter,
                    )

                    if news_result.insufficient_context:
                        skipped += 1
                        logger.info(
                            "Cluster %s skipped: insufficient context for news summary",
                            cluster_id,
                        )
                        continue

                    if not news_result.success:
                        failed += 1
                        logger.warning(
                            "News summary generation failed for cluster %s: %s",
                            cluster_id,
                            news_result.error,
                        )
                        continue

                    # Store news summary in summary_intuition (no deep dive, no ELI20)
                    anti_hype_flags = _compute_anti_hype_flags(content_types, source_count)
                    method_badges = _compute_method_badges(content_types)

                    _update_cluster_stage3(
                        conn,
                        cluster_id,
                        summary_intuition=news_result.summary,
                        summary_intuition_item_ids=item_ids,
                        anti_hype_flags=anti_hype_flags,
                        method_badges=method_badges,
                    )
                    succeeded += 1
                    logger.info(
                        "News summary generated for cluster %s (words=%s confidence=%.2f)",
                        cluster_id,
                        news_result.word_count,
                        news_result.confidence,
                    )
                    continue

            # Generate layered intuition from deep-dive only
            intuition_input = IntuitionInput(
                cluster_title=canonical_title,
                deep_dive_markdown=deep_dive_markdown,
            )
            intuition_result: IntuitionResult = generate_intuition(
                intuition_input, adapter=adapter
            )

            if intuition_result.success:
                summary_deep_dive = _merge_explainers_into_deep_dive(
                    summary_deep_dive_text=summary_deep_dive_text,
                    deep_dive_markdown=deep_dive_markdown,
                    source_count=len(items),
                    eli20=intuition_result.eli20,
                    eli5=intuition_result.eli5,
                )
                # Also compute heuristics (confidence, flags) since we're here
                anti_hype_flags = _compute_anti_hype_flags(content_types, source_count)
                method_badges = _compute_method_badges(content_types)

                _update_cluster_stage3(
                    conn,
                    cluster_id,
                    summary_intuition=intuition_result.eli5,
                    summary_intuition_item_ids=item_ids,
                    summary_deep_dive=summary_deep_dive,
                    summary_deep_dive_item_ids=item_ids,
                    anti_hype_flags=anti_hype_flags,
                    method_badges=method_badges,
                )
                succeeded += 1
                logger.info(
                    "Intuition generated for cluster %s (eli20_words=%s eli5_words=%s "
                    "eli20_rerun=%s eli5_rerun=%s eli20_digit_flag=%s eli5_digit_flag=%s)",
                    cluster_id,
                    intuition_result.eli20_word_count,
                    intuition_result.eli5_word_count,
                    intuition_result.eli20_rerun_shorten,
                    intuition_result.eli5_rerun_shorten,
                    intuition_result.eli20_new_digit_flag,
                    intuition_result.eli5_new_digit_flag,
                )
            else:
                logger.warning(
                    "Intuition generation failed for cluster %s: %s",
                    cluster_id,
                    intuition_result.error,
                )
                failed += 1

        except Exception as e:
            logger.exception("Error generating intuition for cluster %s: %s", cluster_id, e)
            failed += 1

    return GenerateIntuitionResult(
        clusters_processed=processed,
        clusters_succeeded=succeeded,
        clusters_failed=failed,
        clusters_skipped=skipped,
    )


def generate_deep_dives_for_clusters(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    adapter: LLMAdapter | None = None,
) -> GenerateDeepDivesResult:
    """
    Generate deep dives for paper-based clusters (preprints and peer-reviewed).

    Also generates layered intuition from each deep dive and stores:
    - ELI20 in summary_deep_dive payload
    - ELI5 in summary_intuition

    Only applies to clusters with preprint or peer_reviewed content types.
    News articles and press releases don't need deep dives since the article
    itself is the explanation.

    Args:
        conn: Database connection
        limit: Maximum number of clusters to process
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        GenerateDeepDivesResult with processing statistics
    """
    if adapter is None:
        adapter = get_llm_adapter()

    # Only get clusters with paper content types
    clusters = _get_clusters_needing_deep_dive(conn, limit=limit)
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        canonical_title = cluster["canonical_title"]
        takeaway = cluster.get("takeaway")
        processed += 1

        if not takeaway:
            logger.warning("Cluster %s has no takeaway, skipping deep dive", cluster_id)
            skipped += 1
            continue

        try:
            items = _get_cluster_items_for_takeaway(conn, cluster_id)
            items = _ensure_paper_text_hydrated(conn, cluster_id, items)
            fulltext_items, abstract_items = _split_paper_items_by_text_quality(items)
            fulltext_item_ids = [item["item_id"] for item in fulltext_items]
            if not fulltext_items:
                abstract_context = _build_abstract_context(abstract_items)
                if abstract_context:
                    _set_deep_dive_skip_reason(
                        conn,
                        cluster_id,
                        _DEEP_DIVE_SKIP_REASON_ABSTRACT_ONLY,
                    )
                    abstract_result = generate_intuition_from_abstracts(
                        cluster_title=canonical_title,
                        abstracts_text=abstract_context,
                        adapter=adapter,
                    )
                    if abstract_result.success and abstract_result.eli5:
                        _update_cluster_stage3(
                            conn,
                            cluster_id,
                            summary_intuition=abstract_result.eli5,
                            summary_intuition_item_ids=[
                                item["item_id"] for item in abstract_items
                            ],
                        )
                        logger.info(
                            "Cluster %s: generated abstract-only intuition, skipped deep-dive",
                            cluster_id,
                        )
                    else:
                        logger.warning(
                            "Cluster %s: abstract-only intuition failed: %s",
                            cluster_id,
                            abstract_result.error if abstract_context else "no abstract context",
                        )
                else:
                    _set_deep_dive_skip_reason(
                        conn,
                        cluster_id,
                        _DEEP_DIVE_SKIP_REASON_NO_FULLTEXT,
                    )
                    logger.info(
                        "Cluster %s: skipped deep-dive (no full text paper sources)",
                        cluster_id,
                    )
                skipped += 1
                continue

            # Build source summaries for deep dive
            source_summaries = [
                SourceSummary(
                    title=item["title"],
                    snippet=item.get("snippet"),
                    source_name=item.get("source_name"),
                    source_type=item.get("source_type"),
                    full_text=item.get("full_text"),
                )
                for item in fulltext_items
            ]

            # Generate deep dive
            deep_dive_input = DeepDiveInput(
                cluster_title=canonical_title,
                source_summaries=source_summaries,
            )
            deep_dive_result: DeepDiveResult = generate_deep_dive(
                deep_dive_input, adapter=adapter
            )

            if deep_dive_result.success and deep_dive_result.content:
                _set_deep_dive_skip_reason(conn, cluster_id, None)
                deep_dive_markdown = deep_dive_result.content.markdown
                intuition_result = generate_intuition(
                    IntuitionInput(
                        cluster_title=canonical_title,
                        deep_dive_markdown=deep_dive_markdown,
                    ),
                    adapter=adapter,
                )
                summary_deep_dive = deep_dive_to_json(
                    deep_dive_result.content,
                    eli20=intuition_result.eli20 if intuition_result.success else None,
                    eli5=intuition_result.eli5 if intuition_result.success else None,
                )

                _update_cluster_stage3(
                    conn,
                    cluster_id,
                    summary_intuition=(
                        intuition_result.eli5 if intuition_result.success else None
                    ),
                    summary_intuition_item_ids=(
                        fulltext_item_ids if intuition_result.success else None
                    ),
                    summary_deep_dive=summary_deep_dive,
                    summary_deep_dive_item_ids=fulltext_item_ids,
                )
                succeeded += 1
                logger.info(
                    "Deep dive generated for cluster %s (eli20=%s eli5=%s)",
                    cluster_id,
                    "yes" if intuition_result.success and intuition_result.eli20 else "no",
                    "yes" if intuition_result.success and intuition_result.eli5 else "no",
                )
            else:
                _set_deep_dive_skip_reason(
                    conn,
                    cluster_id,
                    _DEEP_DIVE_SKIP_REASON_GEN_FAILED,
                )
                logger.warning(
                    "Deep dive generation failed for cluster %s: %s",
                    cluster_id,
                    deep_dive_result.error,
                )
                failed += 1

        except Exception as e:
            logger.exception("Error generating deep dive for cluster %s: %s", cluster_id, e)
            failed += 1

    return GenerateDeepDivesResult(
        clusters_processed=processed,
        clusters_succeeded=succeeded,
        clusters_failed=failed,
        clusters_skipped=skipped,
    )
