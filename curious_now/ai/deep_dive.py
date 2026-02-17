"""Deep-dive content generation for story clusters.

This module generates structured explainer content that provides
comprehensive context beyond the news headline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


@dataclass
class DeepDiveContent:
    """Deep-dive content in Markdown format."""

    markdown: str
    generated_at: str
    source_count: int


@dataclass
class DeepDiveInput:
    """Input data for deep-dive generation."""

    cluster_title: str
    source_summaries: list[SourceSummary] | None = None
    articles_text: str | None = None  # Pre-formatted full articles text


@dataclass
class SourceSummary:
    """Summary of a source article."""

    title: str
    snippet: str | None = None
    source_name: str | None = None
    source_type: str | None = None  # journalism, journal, preprint, etc.
    full_text: str | None = None  # Full article/abstract text for deep dives


@dataclass
class DeepDiveResult:
    """Result of deep-dive generation."""

    content: DeepDiveContent | None
    raw_json: dict[str, Any]
    confidence: float
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> DeepDiveResult:
        """Create a failure result."""
        return DeepDiveResult(
            content=None,
            raw_json={},
            confidence=0.0,
            model="unknown",
            success=False,
            error=error,
        )


DEEP_DIVE_SYSTEM_PROMPT = """You are a research analyst and science writer producing a technical deep-dive briefing.

Goal: Help an educated, non-expert reader gain a strong working understanding of what the work did, what it found, and how confident we should be—without reading the original paper(s).

Requirements:
- Stay strictly grounded in the provided text. Do not invent details or numbers.
- Prefer concrete methodology and evidence over generic commentary.
- Use technical terms when appropriate, but define any term that is essential to follow the explanation.
- If the sources do not support a detail, omit it rather than guessing.
- If multiple sources disagree, surface the disagreement clearly.
- No hype, no filler."""


DEEP_DIVE_USER_PROMPT_TEMPLATE = """Create a Technical Deep Dive for the following science story.

Objective: Give the reader a thorough, self-contained understanding of the work — what problem it addresses, how it was approached, what was found, and how confident we should be — so they never need to read the original paper(s). Every structural choice you make should serve this objective.

Cluster Title: {cluster_title}

Source Text (articles/abstracts/papers):
{articles_text}

Grounding rules:
- Only include claims supported by the source text.
- Do not invent numbers, datasets, metrics, architectures, or mechanisms.
- If synthesizing multiple sources, merge only when consistent.

Formatting:
- Use Markdown with clear headers and bullet points where helpful.
- Dense but readable. No conversational language.
- Choose whatever section structure best conveys the material. The headers below are suggestions, not requirements — use them, adapt them, or ignore them entirely based on what the sources support:
  Overview / Problem & Context / Methodology / Data & Experimental Setup / Results / Interpretation / Limitations & Uncertainties / What Comes Next

Respond with ONLY the Markdown."""


def _format_articles_text(sources: list[SourceSummary] | None) -> str:
    """Format full article text from sources for the prompt."""
    if not sources:
        return "(No source text available)"

    parts = []
    for i, source in enumerate(sources, 1):
        header_parts = [f"### Source {i}: {source.title}"]
        if source.source_name:
            source_info = source.source_name
            if source.source_type:
                source_info += f" ({source.source_type})"
            header_parts.append(f"*{source_info}*")

        header = "\n".join(header_parts)

        # Use full_text if available, otherwise fall back to snippet
        text = source.full_text or source.snippet or "(No text available)"
        parts.append(f"{header}\n\n{text}")

    return "\n\n---\n\n".join(parts)


def _calculate_confidence(
    content: DeepDiveContent | None,
    input_data: DeepDiveInput,
) -> float:
    """Calculate confidence score for generated deep-dive."""
    if content is None:
        return 0.0

    confidence = 0.7  # Base confidence

    # Check markdown length (word count)
    words = len(content.markdown.split())
    if words < 100:
        confidence -= 0.1
    elif words > 300:
        confidence += 0.1

    # Check for expected sections (headers)
    markdown_lower = content.markdown.lower()
    expected_sections = ["##", "overview", "method", "result", "limitation"]
    sections_found = sum(1 for s in expected_sections if s in markdown_lower)
    confidence += 0.05 * min(sections_found, 4)

    # Source count factor
    if input_data.source_summaries:
        source_count = len(input_data.source_summaries)
        if source_count >= 3:
            confidence += 0.1
        elif source_count == 1:
            confidence -= 0.05

    return max(0.0, min(1.0, confidence))


def generate_deep_dive(
    input_data: DeepDiveInput,
    *,
    adapter: LLMAdapter | None = None,
) -> DeepDiveResult:
    """
    Generate deep-dive content for a story cluster.

    Args:
        input_data: The cluster data to generate deep-dive from
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        DeepDiveResult with the generated content
    """
    if not input_data.cluster_title:
        return DeepDiveResult.failure("No cluster title provided")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build articles text from sources or use pre-formatted text
    if input_data.articles_text:
        articles_text = input_data.articles_text
    else:
        articles_text = _format_articles_text(input_data.source_summaries)

    user_prompt = DEEP_DIVE_USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        articles_text=articles_text,
    )

    # Generate Markdown content
    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=DEEP_DIVE_SYSTEM_PROMPT,
        max_tokens=2000,
        temperature=0.5,
    )

    if not response.success:
        logger.warning("Deep-dive generation failed: %s", response.error)
        return DeepDiveResult.failure(response.error or "Unknown error")

    # Create content from Markdown response
    source_count = len(input_data.source_summaries) if input_data.source_summaries else 0
    content = DeepDiveContent(
        markdown=response.text.strip(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_count=source_count,
    )

    # Calculate confidence
    confidence = _calculate_confidence(content, input_data)

    return DeepDiveResult(
        content=content,
        raw_json={"markdown": content.markdown},
        confidence=confidence,
        model=response.model,
        success=True,
    )


def generate_deep_dive_from_db_data(
    cluster_id: str,
    canonical_title: str,
    sources: list[dict[str, Any]] | None = None,
    articles_text: str | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> DeepDiveResult:
    """
    Generate deep-dive from database query results.

    Args:
        cluster_id: The cluster ID (for logging/reference)
        canonical_title: The cluster's canonical title
        sources: List of source dicts with 'title', 'snippet', 'source_name',
                 'source_type', and optionally 'full_text'
        articles_text: Pre-formatted full articles text (if provided, used directly)
        adapter: LLM adapter to use

    Returns:
        DeepDiveResult with the generated content
    """
    source_summaries = None
    if sources:
        source_summaries = [
            SourceSummary(
                title=s.get("title", ""),
                snippet=s.get("snippet"),
                source_name=s.get("source_name"),
                source_type=s.get("source_type"),
                full_text=s.get("full_text"),
            )
            for s in sources
            if s.get("title")
        ]

    input_data = DeepDiveInput(
        cluster_title=canonical_title,
        source_summaries=source_summaries,
        articles_text=articles_text,
    )

    return generate_deep_dive(input_data, adapter=adapter)


def deep_dive_to_json(
    content: DeepDiveContent,
    *,
    eli20: str | None = None,
    eli5: str | None = None,
) -> dict[str, Any]:
    """Convert DeepDiveContent to JSON-serializable dict for database storage."""
    payload: dict[str, Any] = {
        "markdown": content.markdown,
        "generated_at": content.generated_at,
        "source_count": content.source_count,
    }
    if eli20:
        payload["eli20"] = eli20
    if eli5:
        payload["eli5"] = eli5
    return payload


def deep_dive_from_json(data: dict[str, Any]) -> DeepDiveContent | None:
    """Create DeepDiveContent from JSON dict (e.g., from database)."""
    markdown = data.get("markdown")
    if not markdown or not isinstance(markdown, str):
        return None

    return DeepDiveContent(
        markdown=markdown,
        generated_at=data.get("generated_at", ""),
        source_count=data.get("source_count", 0),
    )
