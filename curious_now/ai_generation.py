"""AI content generation for story clusters.

This module provides functions to generate AI content (takeaways, embeddings,
intuition, deep-dives) for clusters stored in the database.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from curious_now.ai.embeddings import (
    EmbeddingResult,
    generate_cluster_embedding,
    get_embedding_provider,
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
                i.title,
                i.snippet,
                s.name AS source_name,
                i.content_type AS source_type
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
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE story_clusters
            SET takeaway = %s,
                takeaway_supporting_item_ids = %s,
                updated_at = now()
            WHERE id = %s;
            """,
            (takeaway, item_ids, cluster_id),
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

            # Build input
            item_summaries = [
                ItemSummary(
                    title=item["title"],
                    snippet=item.get("snippet"),
                    source_name=item.get("source_name"),
                    source_type=item.get("source_type"),
                )
                for item in items
            ]

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

            # Update cluster (no item IDs for now, would need to track which items
            # were used)
            _update_cluster_takeaway(conn, cluster_id, result.takeaway, [])
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
            result: EmbeddingResult = generate_cluster_embedding(
                cluster_id=str(cluster_id),
                canonical_title=canonical_title,
                takeaway=takeaway,
                topic_names=topics if topics else None,
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
