"""Deep-dive content generation for story clusters.

This module generates structured explainer content that provides
comprehensive context beyond the news headline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


@dataclass
class DeepDiveContent:
    """Structured deep-dive content."""

    what_happened: str
    why_it_matters: str
    background: str
    limitations: list[str]
    whats_next: str
    related_concepts: list[str]
    generated_at: str
    source_count: int


@dataclass
class DeepDiveInput:
    """Input data for deep-dive generation."""

    cluster_title: str
    takeaway: str | None = None
    source_summaries: list[SourceSummary] | None = None
    glossary_terms: list[str] | None = None
    topic_names: list[str] | None = None
    related_cluster_titles: list[str] | None = None


@dataclass
class SourceSummary:
    """Summary of a source article."""

    title: str
    snippet: str | None = None
    source_name: str | None = None
    source_type: str | None = None  # journalism, journal, preprint, etc.


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


DEEP_DIVE_SYSTEM_PROMPT = """You are a science educator creating comprehensive explainer content.

Your goal is to give readers everything they need to understand a science story:
- Context they need to understand significance
- Honest acknowledgment of limitations
- Forward-looking perspective on what comes next

Guidelines:
- Write for educated non-specialists (smart but not experts)
- Be factual and specific, citing details from sources
- No hype or exaggeration
- Acknowledge uncertainty where it exists
- Keep each section concise but informative"""


DEEP_DIVE_USER_PROMPT_TEMPLATE = """Create a deep-dive explainer for this science story.

Cluster Title: {cluster_title}

Key Takeaway: {takeaway}

{sources_section}
{context_section}

Generate a JSON response with this exact structure:
{{
  "what_happened": "2-3 sentences describing the core finding/event factually",
  "why_it_matters": "2-3 sentences explaining the significance and implications",
  "background": "3-4 sentences providing context needed to understand this",
  "limitations": ["limitation 1", "limitation 2", "limitation 3"],
  "whats_next": "2-3 sentences about future directions or next steps",
  "related_concepts": ["concept1", "concept2", "concept3"]
}}

Requirements:
- Each section should be specific to THIS story, not generic
- Limitations should include real caveats (cost, time, uncertainty, etc.)
- Related concepts should be terms readers might want to learn more about

Respond with ONLY the JSON object, no other text."""


def _format_sources(sources: list[SourceSummary] | None) -> str:
    """Format source summaries for the prompt."""
    if not sources:
        return ""

    formatted = "Source Articles:\n"
    for i, source in enumerate(sources[:5], 1):  # Limit to 5 sources
        lines = [f"{i}. {source.title}"]
        if source.source_name:
            source_info = source.source_name
            if source.source_type:
                source_info += f" ({source.source_type})"
            lines.append(f"   Source: {source_info}")
        if source.snippet:
            snippet = source.snippet[:400] + "..." if len(source.snippet) > 400 else source.snippet
            lines.append(f"   Summary: {snippet}")
        formatted += "\n".join(lines) + "\n\n"

    return formatted


def _format_context(
    glossary_terms: list[str] | None,
    topic_names: list[str] | None,
    related_clusters: list[str] | None,
) -> str:
    """Format context information for the prompt."""
    parts = []

    if topic_names:
        parts.append(f"Topics: {', '.join(topic_names)}")

    if glossary_terms:
        parts.append(f"Key Terms: {', '.join(glossary_terms[:5])}")

    if related_clusters:
        parts.append(f"Related Stories: {', '.join(related_clusters[:3])}")

    if not parts:
        return ""

    return "Context:\n" + "\n".join(parts) + "\n"


def _parse_deep_dive_json(text: str) -> dict[str, Any] | None:
    """Parse deep-dive JSON from LLM response."""
    text = text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse deep-dive JSON: %s", e)
        return None


def _validate_deep_dive_content(data: dict[str, Any]) -> DeepDiveContent | None:
    """Validate and create DeepDiveContent from parsed JSON."""
    required_fields = ["what_happened", "why_it_matters", "background", "whats_next"]

    for field_name in required_fields:
        if field_name not in data or not isinstance(data[field_name], str):
            logger.warning("Missing or invalid field: %s", field_name)
            return None

    # Get limitations as list
    limitations = data.get("limitations", [])
    if isinstance(limitations, str):
        limitations = [limitations]
    elif not isinstance(limitations, list):
        limitations = []

    # Get related concepts as list
    related = data.get("related_concepts", [])
    if isinstance(related, str):
        related = [related]
    elif not isinstance(related, list):
        related = []

    return DeepDiveContent(
        what_happened=data["what_happened"],
        why_it_matters=data["why_it_matters"],
        background=data["background"],
        limitations=[str(lim) for lim in limitations],
        whats_next=data["whats_next"],
        related_concepts=[str(c) for c in related],
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_count=0,  # Will be set by caller
    )


def _calculate_confidence(
    content: DeepDiveContent | None,
    input_data: DeepDiveInput,
) -> float:
    """Calculate confidence score for generated deep-dive."""
    if content is None:
        return 0.0

    confidence = 0.7  # Base confidence

    # Check section lengths
    sections = [
        content.what_happened,
        content.why_it_matters,
        content.background,
        content.whats_next,
    ]

    for section in sections:
        words = len(section.split())
        if words < 10:
            confidence -= 0.05
        elif words > 100:
            confidence -= 0.02

    # Limitations present
    if len(content.limitations) >= 2:
        confidence += 0.1
    elif len(content.limitations) == 0:
        confidence -= 0.1

    # Related concepts present
    if len(content.related_concepts) >= 2:
        confidence += 0.05

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

    # Build the prompt
    takeaway = input_data.takeaway or "See sources for details."
    sources_section = _format_sources(input_data.source_summaries)
    context_section = _format_context(
        input_data.glossary_terms,
        input_data.topic_names,
        input_data.related_cluster_titles,
    )

    user_prompt = DEEP_DIVE_USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        takeaway=takeaway,
        sources_section=sources_section,
        context_section=context_section,
    )

    # Generate completion
    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=DEEP_DIVE_SYSTEM_PROMPT,
        max_tokens=1000,
        temperature=0.5,  # Lower temp for more structured output
    )

    if not response.success:
        logger.warning("Deep-dive generation failed: %s", response.error)
        return DeepDiveResult.failure(response.error or "Unknown error")

    # Parse the JSON response
    raw_json = _parse_deep_dive_json(response.text)
    if raw_json is None:
        return DeepDiveResult.failure("Failed to parse JSON response")

    # Validate and create content
    content = _validate_deep_dive_content(raw_json)
    if content is None:
        return DeepDiveResult.failure("Invalid deep-dive content structure")

    # Set source count
    source_count = len(input_data.source_summaries) if input_data.source_summaries else 0
    content = DeepDiveContent(
        what_happened=content.what_happened,
        why_it_matters=content.why_it_matters,
        background=content.background,
        limitations=content.limitations,
        whats_next=content.whats_next,
        related_concepts=content.related_concepts,
        generated_at=content.generated_at,
        source_count=source_count,
    )

    # Calculate confidence
    confidence = _calculate_confidence(content, input_data)

    return DeepDiveResult(
        content=content,
        raw_json=raw_json,
        confidence=confidence,
        model=response.model,
        success=True,
    )


def generate_deep_dive_from_db_data(
    cluster_id: str,
    canonical_title: str,
    takeaway: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    glossary_terms: list[str] | None = None,
    topic_names: list[str] | None = None,
    related_cluster_titles: list[str] | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> DeepDiveResult:
    """
    Generate deep-dive from database query results.

    Args:
        cluster_id: The cluster ID
        canonical_title: The cluster's canonical title
        takeaway: Optional pre-generated takeaway
        sources: List of source dicts with 'title', 'snippet', 'source_name', 'source_type'
        glossary_terms: List of glossary term strings
        topic_names: Optional list of topic names
        related_cluster_titles: Optional list of related cluster titles
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
            )
            for s in sources
            if s.get("title")
        ]

    input_data = DeepDiveInput(
        cluster_title=canonical_title,
        takeaway=takeaway,
        source_summaries=source_summaries,
        glossary_terms=glossary_terms,
        topic_names=topic_names,
        related_cluster_titles=related_cluster_titles,
    )

    return generate_deep_dive(input_data, adapter=adapter)


def deep_dive_to_json(content: DeepDiveContent) -> dict[str, Any]:
    """Convert DeepDiveContent to JSON-serializable dict for database storage."""
    return {
        "what_happened": content.what_happened,
        "why_it_matters": content.why_it_matters,
        "background": content.background,
        "limitations": content.limitations,
        "whats_next": content.whats_next,
        "related_concepts": content.related_concepts,
        "generated_at": content.generated_at,
        "source_count": content.source_count,
    }


def deep_dive_from_json(data: dict[str, Any]) -> DeepDiveContent | None:
    """Create DeepDiveContent from JSON dict (e.g., from database)."""
    return _validate_deep_dive_content(data)
