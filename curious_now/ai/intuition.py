"""Intuition field generation for story clusters.

This module generates plain-language explanations that build mental models
for non-experts using analogies and simplified concepts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


@dataclass
class IntuitionInput:
    """Input data for intuition generation."""

    cluster_title: str
    takeaway: str | None = None
    technical_snippets: list[str] | None = None
    glossary_terms: list[GlossaryTerm] | None = None
    topic_names: list[str] | None = None


@dataclass
class GlossaryTerm:
    """A glossary term with definition."""

    term: str
    definition: str


@dataclass
class IntuitionResult:
    """Result of intuition generation."""

    intuition: str
    analogies_used: list[str]
    confidence: float
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> IntuitionResult:
        """Create a failure result."""
        return IntuitionResult(
            intuition="",
            analogies_used=[],
            confidence=0.0,
            model="unknown",
            success=False,
            error=error,
        )


INTUITION_SYSTEM_PROMPT = """You are explaining science concepts to a smart, \
curious friend who isn't a scientist.

Your goal is to build understanding, not just awareness. Use:
- Analogies to everyday things
- Simple comparisons
- Concrete examples

Avoid:
- Jargon and technical terms (unless you explain them)
- Hedging and unnecessary caveats
- Vague statements like "this is important" without explaining why
- Starting with "Imagine" or "Think of it like" - just use the analogy directly"""


INTUITION_USER_PROMPT_TEMPLATE = """Topic: {cluster_title}

Key Point: {takeaway}

{technical_section}
{glossary_section}

Write 2-3 sentences (100-150 words) that:
1. Use an analogy or comparison to everyday things
2. Explain the core concept in plain language
3. Highlight why this technical detail matters

At the end, list any analogies you used in brackets, like: [Analogies: scissors, lock and key]

Write ONLY the explanation followed by the analogies list."""


def _format_technical_snippets(snippets: list[str] | None) -> str:
    """Format technical snippets for the prompt."""
    if not snippets:
        return ""

    formatted = "Technical Details:\n"
    for snippet in snippets[:3]:  # Limit to 3 snippets
        truncated = snippet[:300] + "..." if len(snippet) > 300 else snippet
        formatted += f"- {truncated}\n"
    return formatted


def _format_glossary(terms: list[GlossaryTerm] | None) -> str:
    """Format glossary terms for the prompt."""
    if not terms:
        return ""

    formatted = "Related Terms:\n"
    for term in terms[:5]:  # Limit to 5 terms
        formatted += f"- {term.term}: {term.definition}\n"
    return formatted


def _extract_analogies(text: str) -> tuple[str, list[str]]:
    """Extract analogies list from the response text."""
    analogies: list[str] = []
    clean_text = text

    # Look for [Analogies: ...] at the end
    if "[Analogies:" in text:
        start = text.find("[Analogies:")
        end = text.find("]", start)
        if end > start:
            analogies_str = text[start + 11:end].strip()
            analogies = [a.strip() for a in analogies_str.split(",") if a.strip()]
            clean_text = text[:start].strip()

    # Also check for [Analogy: ...] (singular)
    elif "[Analogy:" in text:
        start = text.find("[Analogy:")
        end = text.find("]", start)
        if end > start:
            analogies_str = text[start + 9:end].strip()
            analogies = [a.strip() for a in analogies_str.split(",") if a.strip()]
            clean_text = text[:start].strip()

    return clean_text, analogies


def _calculate_confidence(intuition: str, input_data: IntuitionInput) -> float:
    """Calculate confidence score for generated intuition."""
    confidence = 0.75  # Base confidence

    # Length factors
    word_count = len(intuition.split())
    if word_count < 30:
        confidence -= 0.15
    elif word_count > 200:
        confidence -= 0.1
    elif 50 <= word_count <= 150:
        confidence += 0.1

    # Has takeaway provides more context
    if input_data.takeaway:
        confidence += 0.05

    # Has technical snippets to work from
    if input_data.technical_snippets:
        confidence += 0.05

    # Check for jargon indicators (might indicate poor simplification)
    jargon_indicators = [
        "et al", "p-value", "statistically significant",
        "methodology", "paradigm", "pursuant to"
    ]
    intuition_lower = intuition.lower()
    for indicator in jargon_indicators:
        if indicator in intuition_lower:
            confidence -= 0.05

    return max(0.0, min(1.0, confidence))


def generate_intuition(
    input_data: IntuitionInput,
    *,
    adapter: LLMAdapter | None = None,
) -> IntuitionResult:
    """
    Generate an intuition explanation for a story cluster.

    Args:
        input_data: The cluster data to generate intuition from
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        IntuitionResult with the generated explanation
    """
    if not input_data.cluster_title:
        return IntuitionResult.failure("No cluster title provided")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    takeaway = input_data.takeaway or input_data.cluster_title
    technical_section = _format_technical_snippets(input_data.technical_snippets)
    glossary_section = _format_glossary(input_data.glossary_terms)

    user_prompt = INTUITION_USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        takeaway=takeaway,
        technical_section=technical_section,
        glossary_section=glossary_section,
    )

    # Generate completion
    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=INTUITION_SYSTEM_PROMPT,
        max_tokens=400,
        temperature=0.7,
    )

    if not response.success:
        logger.warning("Intuition generation failed: %s", response.error)
        return IntuitionResult.failure(response.error or "Unknown error")

    # Process the response
    raw_text = response.text.strip()
    intuition, analogies = _extract_analogies(raw_text)

    # Clean up quotes
    if intuition.startswith('"') and intuition.endswith('"'):
        intuition = intuition[1:-1]

    # Calculate confidence
    confidence = _calculate_confidence(intuition, input_data)

    return IntuitionResult(
        intuition=intuition,
        analogies_used=analogies,
        confidence=confidence,
        model=response.model,
        success=True,
    )


def generate_intuition_from_db_data(
    cluster_id: str,
    canonical_title: str,
    takeaway: str | None = None,
    technical_snippets: list[str] | None = None,
    glossary_terms: list[dict[str, Any]] | None = None,
    topic_names: list[str] | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> IntuitionResult:
    """
    Generate intuition from database query results.

    Args:
        cluster_id: The cluster ID
        canonical_title: The cluster's canonical title
        takeaway: Optional pre-generated takeaway
        technical_snippets: List of technical text from sources
        glossary_terms: List of dicts with 'term' and 'definition' keys
        topic_names: Optional list of topic names
        adapter: LLM adapter to use

    Returns:
        IntuitionResult with the generated explanation
    """
    terms = None
    if glossary_terms:
        terms = [
            GlossaryTerm(
                term=t.get("term", ""),
                definition=t.get("definition", ""),
            )
            for t in glossary_terms
            if t.get("term") and t.get("definition")
        ]

    input_data = IntuitionInput(
        cluster_title=canonical_title,
        takeaway=takeaway,
        technical_snippets=technical_snippets,
        glossary_terms=terms,
        topic_names=topic_names,
    )

    return generate_intuition(input_data, adapter=adapter)
