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

from curious_now.ai.embeddings import (
    ClusterEmbeddingInput,
    EmbeddingResult,
    generate_cluster_embedding,
    get_embedding_provider,
)
from curious_now.ai.deep_dive import (
    DeepDiveInput,
    DeepDiveResult,
    SourceSummary,
    deep_dive_to_json,
    generate_deep_dive,
)
from curious_now.ai.intuition import (
    IntuitionInput,
    IntuitionResult,
    generate_intuition,
)
from curious_now.ai.llm_adapter import LLMAdapter, get_llm_adapter
from curious_now.ai.takeaways import (
    ItemSummary,
    TakeawayInput,
    TakeawayResult,
    generate_takeaway,
)

logger = logging.getLogger(__name__)


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


def _get_clusters_needing_takeaways(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get clusters that need takeaway generation."""
    with conn.cursor() as cur:
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
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                i.id AS item_id,
                i.title,
                i.snippet,
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


def _get_cluster_topics(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> list[str]:
    """Get topic names for a cluster."""
    with conn.cursor() as cur:
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
    with conn.cursor() as cur:
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

    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


def _compute_source_text_hash(text: str) -> str:
    """Compute hash of source text for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _upsert_cluster_embedding(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    embedding: list[float],
    model: str,
    source_text_hash: str,
) -> None:
    """Insert or update cluster embedding."""
    with conn.cursor() as cur:
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
    with conn.cursor() as cur:
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
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS cluster_id,
                c.canonical_title,
                c.takeaway,
                c.distinct_source_count
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


def _get_cluster_content_types(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
) -> list[str]:
    """Get distinct content types for items in a cluster."""
    with conn.cursor() as cur:
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


def _get_cluster_snippets(
    conn: psycopg.Connection[Any],
    cluster_id: UUID,
    limit: int = 5,
) -> list[str]:
    """Get technical snippets from cluster items for intuition generation."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.snippet
            FROM cluster_items ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.cluster_id = %s
              AND i.snippet IS NOT NULL
              AND LENGTH(i.snippet) > 50
            ORDER BY ci.role ASC, i.published_at DESC NULLS LAST
            LIMIT %s;
            """,
            (cluster_id, limit),
        )
        return [row["snippet"] for row in cur.fetchall()]


def _compute_confidence_band(
    content_types: list[str],
    source_count: int,
) -> str | None:
    """
    Compute confidence band based on evidence types.

    Returns: 'early', 'growing', 'established', or None
    """
    has_peer_reviewed = "peer_reviewed" in content_types
    has_preprint = "preprint" in content_types
    has_report = "report" in content_types
    has_primary = has_peer_reviewed or has_preprint or has_report

    if has_peer_reviewed and source_count >= 3:
        return "established"
    elif has_primary and source_count >= 2:
        return "growing"
    elif source_count >= 1:
        return "early"
    return None


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
    confidence_band: str | None = None,
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

    if confidence_band is not None:
        updates.append("confidence_band = %s")
        params.append(confidence_band)

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

            # Get topics
            topics = _get_cluster_topics(conn, cluster_id)

            # Get snippets for intuition
            snippets = _get_cluster_snippets(conn, cluster_id)

            # ─────────────────────────────────────────────────────────────
            # Generate intuition
            # ─────────────────────────────────────────────────────────────
            intuition_input = IntuitionInput(
                cluster_title=canonical_title,
                takeaway=takeaway,
                technical_snippets=snippets if snippets else None,
                topic_names=topics if topics else None,
            )
            intuition_result: IntuitionResult = generate_intuition(
                intuition_input, adapter=adapter
            )

            summary_intuition = None
            if intuition_result.success:
                summary_intuition = intuition_result.intuition
            else:
                logger.warning(
                    "Intuition generation failed for cluster %s: %s",
                    cluster_id,
                    intuition_result.error,
                )

            # ─────────────────────────────────────────────────────────────
            # Generate deep-dive
            # ─────────────────────────────────────────────────────────────
            source_summaries = [
                SourceSummary(
                    title=item["title"],
                    snippet=item.get("snippet"),
                    source_name=item.get("source_name"),
                    source_type=item.get("source_type"),
                )
                for item in items
            ]

            deep_dive_input = DeepDiveInput(
                cluster_title=canonical_title,
                takeaway=takeaway,
                source_summaries=source_summaries,
                topic_names=topics if topics else None,
            )
            deep_dive_result: DeepDiveResult = generate_deep_dive(
                deep_dive_input, adapter=adapter
            )

            summary_deep_dive = None
            limitations = None
            if deep_dive_result.success and deep_dive_result.content:
                summary_deep_dive = deep_dive_to_json(deep_dive_result.content)
                limitations = deep_dive_result.content.limitations
            else:
                logger.warning(
                    "Deep-dive generation failed for cluster %s: %s",
                    cluster_id,
                    deep_dive_result.error,
                )

            # ─────────────────────────────────────────────────────────────
            # Compute heuristics
            # ─────────────────────────────────────────────────────────────
            confidence_band = _compute_confidence_band(content_types, source_count)
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
                confidence_band=confidence_band,
                anti_hype_flags=anti_hype_flags,
                method_badges=method_badges,
                limitations=limitations,
            )

            succeeded += 1
            logger.info(
                "Stage 3 enrichment complete for cluster %s "
                "(intuition: %s, deep-dive: %s, confidence: %s)",
                cluster_id,
                "yes" if summary_intuition else "no",
                "yes" if summary_deep_dive else "no",
                confidence_band,
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
