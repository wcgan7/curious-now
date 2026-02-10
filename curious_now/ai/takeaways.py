"""Takeaway generation for story clusters.

This module generates AI-powered 1-2 sentence summaries explaining
what a story means and why it matters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


# Maximum character length for takeaways
MAX_TAKEAWAY_LENGTH = 280

# Minimum content requirements for takeaway generation
MIN_TOTAL_CONTENT_CHARS = 80  # Minimum total chars across title + snippets
INSUFFICIENT_CONTEXT_MARKER = "INSUFFICIENT_CONTEXT"


@dataclass
class TakeawayInput:
    """Input data for takeaway generation."""

    cluster_title: str
    items: list[ItemSummary]
    topic_names: list[str] | None = None


@dataclass
class ItemSummary:
    """Summary of an item for takeaway generation."""

    title: str
    snippet: str | None = None
    source_name: str | None = None
    source_type: str | None = None  # journalism, journal, preprint, etc.
    published_at: str | None = None


@dataclass
class TakeawayResult:
    """Result of takeaway generation."""

    takeaway: str
    confidence: float
    supporting_item_ids: list[str]
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> TakeawayResult:
        """Create a failure result."""
        return TakeawayResult(
            takeaway="",
            confidence=0.0,
            supporting_item_ids=[],
            model="unknown",
            success=False,
            error=error,
        )


TAKEAWAY_SYSTEM_PROMPT = """You are a science journalist writing for curious non-scientists.
Your job is to explain complex science stories in plain language.

Rules:
- Use plain language, no jargon
- Be specific, not vague
- Focus on implications for the reader
- Never start with "Scientists" or "Researchers" - vary your openings
- Do not use hype words like "breakthrough", "revolutionary", "game-changing"
- Acknowledge uncertainty when the research is preliminary"""


TAKEAWAY_USER_PROMPT_TEMPLATE = """Given these related news articles about a science story:

Cluster Title: {cluster_title}

Articles:
{articles_text}

{topics_section}

Write a 1-2 sentence takeaway that explains:
1. What happened (the core finding/event)
2. Why it matters (the significance)

Requirements:
- Maximum {max_length} characters
- Plain language, no jargon
- Be specific about what this means for people
- Do NOT invent or hallucinate any details not present in the articles
- If there is not enough information to write a meaningful takeaway, output exactly: INSUFFICIENT_CONTEXT

Respond with ONLY the takeaway text (or INSUFFICIENT_CONTEXT), nothing else."""


def _format_articles(items: list[ItemSummary]) -> str:
    """Format articles for the prompt."""
    parts = []
    for i, item in enumerate(items[:5], 1):  # Limit to top 5 items
        lines = [f"{i}. {item.title}"]
        if item.source_name:
            lines.append(f"   Source: {item.source_name}")
        if item.snippet:
            # Truncate snippet to reasonable length
            snippet = item.snippet[:300] + "..." if len(item.snippet) > 300 else item.snippet
            lines.append(f"   Summary: {snippet}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _format_topics(topic_names: list[str] | None) -> str:
    """Format topics section for the prompt."""
    if not topic_names:
        return ""
    return f"Topics: {', '.join(topic_names)}\n"


def _calculate_total_content_length(input_data: TakeawayInput) -> int:
    """Calculate total content length from title and snippets."""
    total = len(input_data.cluster_title or "")
    for item in input_data.items:
        total += len(item.title or "")
        total += len(item.snippet or "")
    return total


def generate_takeaway(
    input_data: TakeawayInput,
    *,
    adapter: LLMAdapter | None = None,
    max_length: int = MAX_TAKEAWAY_LENGTH,
) -> TakeawayResult:
    """
    Generate a takeaway for a story cluster.

    Args:
        input_data: The cluster data to generate takeaway from
        adapter: LLM adapter to use (defaults to configured adapter)
        max_length: Maximum character length for takeaway

    Returns:
        TakeawayResult with the generated takeaway
    """
    if not input_data.items:
        return TakeawayResult.failure("No items provided for takeaway generation")

    if not input_data.cluster_title:
        return TakeawayResult.failure("No cluster title provided")

    # Content gating: check minimum content threshold
    total_content = _calculate_total_content_length(input_data)
    if total_content < MIN_TOTAL_CONTENT_CHARS:
        logger.info(
            "Takeaway skipped: insufficient content (%d chars < %d minimum) for '%s'",
            total_content,
            MIN_TOTAL_CONTENT_CHARS,
            input_data.cluster_title[:50],
        )
        return TakeawayResult.failure("Insufficient content for takeaway generation")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    articles_text = _format_articles(input_data.items)
    topics_section = _format_topics(input_data.topic_names)

    user_prompt = TAKEAWAY_USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        articles_text=articles_text,
        topics_section=topics_section,
        max_length=max_length,
    )

    # Generate completion
    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=TAKEAWAY_SYSTEM_PROMPT,
        max_tokens=200,
        temperature=0.7,
    )

    if not response.success:
        logger.warning("Takeaway generation failed: %s", response.error)
        return TakeawayResult.failure(response.error or "Unknown error")

    # Process the response
    takeaway = response.text.strip()

    # Remove quotes if the model wrapped in quotes
    if takeaway.startswith('"') and takeaway.endswith('"'):
        takeaway = takeaway[1:-1]
    if takeaway.startswith("'") and takeaway.endswith("'"):
        takeaway = takeaway[1:-1]

    # Check if LLM indicated insufficient context
    if INSUFFICIENT_CONTEXT_MARKER in takeaway.upper():
        logger.info(
            "Takeaway skipped: LLM returned insufficient context for '%s'",
            input_data.cluster_title[:50],
        )
        return TakeawayResult.failure("LLM indicated insufficient context")

    # Truncate if too long (LLM might exceed limit)
    if len(takeaway) > max_length:
        # Try to truncate at sentence boundary
        truncated = takeaway[:max_length]
        last_period = truncated.rfind(".")
        last_question = truncated.rfind("?")
        last_exclaim = truncated.rfind("!")
        best_end = max(last_period, last_question, last_exclaim)
        if best_end > max_length // 2:
            takeaway = truncated[: best_end + 1]
        else:
            takeaway = truncated.rstrip() + "..."

    # Calculate confidence based on response quality
    confidence = _calculate_confidence(takeaway, input_data)

    # Get supporting item IDs (all items used in generation)
    supporting_ids = [str(i) for i in range(len(input_data.items[:5]))]

    return TakeawayResult(
        takeaway=takeaway,
        confidence=confidence,
        supporting_item_ids=supporting_ids,
        model=response.model,
        success=True,
    )


def _calculate_confidence(takeaway: str, input_data: TakeawayInput) -> float:
    """
    Calculate confidence score for a generated takeaway.

    Factors:
    - Length (too short or too long reduces confidence)
    - Number of source items (more sources = higher confidence)
    - Contains hedging language for preliminary findings
    - Doesn't contain hype words
    """
    confidence = 0.8  # Base confidence

    # Length factors
    length = len(takeaway)
    if length < 50:
        confidence -= 0.15
    elif length < 100:
        confidence -= 0.05
    elif length > MAX_TAKEAWAY_LENGTH:
        confidence -= 0.1

    # Source count factor
    num_items = len(input_data.items)
    if num_items >= 3:
        confidence += 0.1
    elif num_items == 1:
        confidence -= 0.1

    # Hype word penalty
    hype_words = ["breakthrough", "revolutionary", "game-changing", "miracle", "cure"]
    takeaway_lower = takeaway.lower()
    for word in hype_words:
        if word in takeaway_lower:
            confidence -= 0.1
            break

    # Ensure confidence is in valid range
    return max(0.0, min(1.0, confidence))


def generate_takeaway_from_db_data(
    cluster_id: str,
    canonical_title: str,
    items: list[dict[str, Any]],
    topic_names: list[str] | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> TakeawayResult:
    """
    Generate takeaway from database query results.

    This is a convenience function that accepts data in the format
    typically returned by database queries.

    Args:
        cluster_id: The cluster ID
        canonical_title: The cluster's canonical title
        items: List of item dicts with 'title', 'snippet', 'source_name', 'published_at'
        topic_names: Optional list of topic names
        adapter: LLM adapter to use

    Returns:
        TakeawayResult with the generated takeaway
    """
    item_summaries = [
        ItemSummary(
            title=item.get("title", ""),
            snippet=item.get("snippet"),
            source_name=item.get("source_name"),
            published_at=str(item["published_at"]) if item.get("published_at") else None,
        )
        for item in items
    ]

    input_data = TakeawayInput(
        cluster_title=canonical_title,
        items=item_summaries,
        topic_names=topic_names,
    )

    return generate_takeaway(input_data, adapter=adapter)


async def generate_takeaway_batch(
    clusters: list[TakeawayInput],
    *,
    adapter: LLMAdapter | None = None,
) -> list[TakeawayResult]:
    """
    Generate takeaways for multiple clusters.

    Note: Currently processes sequentially. Future optimization
    could use async/parallel processing.

    Args:
        clusters: List of TakeawayInput objects
        adapter: LLM adapter to use

    Returns:
        List of TakeawayResult objects in same order as input
    """
    if adapter is None:
        adapter = get_llm_adapter()

    results = []
    for cluster in clusters:
        result = generate_takeaway(cluster, adapter=adapter)
        results.append(result)

    return results
