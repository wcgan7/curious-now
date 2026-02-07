"""LLM-based topic classification for story clusters.

This module provides semantic topic classification using LLMs,
designed to work as a fallback when phrase matching produces
low-confidence or no results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, get_llm_adapter

logger = logging.getLogger(__name__)


@dataclass
class TopicDefinition:
    """A topic available for classification."""

    name: str
    description: str | None = None


@dataclass
class TopicMatch:
    """A matched topic with confidence score."""

    topic_name: str
    score: float  # 0.0 to 1.0
    reasoning: str | None = None


@dataclass
class ClassificationResult:
    """Result of topic classification."""

    topics: list[TopicMatch]
    model: str
    success: bool = True
    error: str | None = None
    out_of_domain: bool = False  # True if content is outside science domain
    out_of_domain_reason: str | None = None

    @staticmethod
    def failure(error: str) -> ClassificationResult:
        """Create a failure result."""
        return ClassificationResult(
            topics=[],
            model="unknown",
            success=False,
            error=error,
        )


CLASSIFICATION_SYSTEM_PROMPT = """You are a topic classifier for a science and technology news aggregator.
Your job is to identify which topics best describe a given story.

Rules:
- Only assign topics that are clearly relevant
- A story can match 1-3 topics (not more)
- If a story doesn't clearly fit any topic, return an empty list
- Prefer specific topics over general ones when both apply
- Consider the main focus, not just mentioned keywords
- If content is NOT about science/technology (e.g., sports, entertainment, politics without science angle), mark it as out_of_domain"""


CLASSIFICATION_USER_PROMPT_TEMPLATE = """Classify this story into the most relevant science/technology topics.

Story Title: {title}

Story Content:
{content}

Available Topics:
{topics_list}

Return a JSON object with this exact structure:
{{
  "out_of_domain": false,
  "out_of_domain_reason": null,
  "topics": [
    {{"name": "TopicName", "score": 0.9, "reasoning": "Brief explanation"}},
    ...
  ]
}}

Rules:
- "out_of_domain": set to true if the content is NOT about science or technology (e.g., sports, entertainment, celebrity news, pure politics)
- "out_of_domain_reason": brief explanation if out_of_domain is true (e.g., "Sports event", "Entertainment news")
- "name" must exactly match one of the available topic names
- "score" is confidence from 0.0 to 1.0 (only include topics with score >= 0.6)
- Include at most 3 topics
- If no topics clearly match but content IS science-related, return empty topics array with out_of_domain: false

Respond with ONLY the JSON object, no other text."""


def _format_topics_list(topics: list[TopicDefinition]) -> str:
    """Format topics for the prompt."""
    lines = []
    for topic in topics:
        if topic.description:
            lines.append(f"- {topic.name}: {topic.description}")
        else:
            lines.append(f"- {topic.name}")
    return "\n".join(lines)


@dataclass
class ParsedResponse:
    """Parsed LLM classification response."""

    topics: list[TopicMatch]
    out_of_domain: bool
    out_of_domain_reason: str | None


def _parse_classification_response(
    response_json: dict[str, Any] | None,
    valid_topic_names: set[str],
) -> ParsedResponse:
    """Parse and validate the LLM response."""
    if not response_json:
        return ParsedResponse(topics=[], out_of_domain=False, out_of_domain_reason=None)

    # Check out_of_domain flag
    out_of_domain = bool(response_json.get("out_of_domain", False))
    out_of_domain_reason = response_json.get("out_of_domain_reason")
    if not isinstance(out_of_domain_reason, str):
        out_of_domain_reason = None

    topics_raw = response_json.get("topics", [])
    if not isinstance(topics_raw, list):
        return ParsedResponse(
            topics=[],
            out_of_domain=out_of_domain,
            out_of_domain_reason=out_of_domain_reason,
        )

    matches: list[TopicMatch] = []
    for item in topics_raw:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "")
        if not isinstance(name, str) or name not in valid_topic_names:
            logger.debug("Skipping invalid topic name: %s", name)
            continue

        score = item.get("score", 0.0)
        if isinstance(score, (int, float)):
            score = float(score)
        else:
            score = 0.0

        # Only include high-confidence matches
        if score < 0.6:
            continue

        reasoning = item.get("reasoning")
        if not isinstance(reasoning, str):
            reasoning = None

        matches.append(TopicMatch(topic_name=name, score=score, reasoning=reasoning))

    # Sort by score descending and limit to 3
    matches.sort(key=lambda x: -x.score)
    return ParsedResponse(
        topics=matches[:3],
        out_of_domain=out_of_domain,
        out_of_domain_reason=out_of_domain_reason,
    )


def classify_topics(
    title: str,
    content: str,
    available_topics: list[TopicDefinition],
    *,
    adapter: LLMAdapter | None = None,
) -> ClassificationResult:
    """
    Classify a story into topics using LLM.

    Args:
        title: The story/cluster title
        content: The story content (search text, snippets, etc.)
        available_topics: List of topics to classify into
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        ClassificationResult with matched topics and scores
    """
    if not title and not content:
        return ClassificationResult.failure("No title or content provided")

    if not available_topics:
        return ClassificationResult.failure("No topics available for classification")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    topics_list = _format_topics_list(available_topics)

    # Truncate content if too long
    max_content_len = 2000
    if len(content) > max_content_len:
        content = content[:max_content_len] + "..."

    user_prompt = CLASSIFICATION_USER_PROMPT_TEMPLATE.format(
        title=title,
        content=content or "(No additional content)",
        topics_list=topics_list,
    )

    # Generate completion with JSON output
    response_json = adapter.complete_json(
        user_prompt,
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
        max_tokens=500,
    )

    if response_json is None:
        logger.warning("LLM topic classification returned no JSON")
        return ClassificationResult.failure("Failed to parse LLM response as JSON")

    # Parse and validate response
    valid_names = {t.name for t in available_topics}
    parsed = _parse_classification_response(response_json, valid_names)

    return ClassificationResult(
        topics=parsed.topics,
        model=adapter.name,
        success=True,
        out_of_domain=parsed.out_of_domain,
        out_of_domain_reason=parsed.out_of_domain_reason,
    )


def classify_cluster_topics(
    cluster_title: str,
    search_text: str,
    topics_from_db: list[dict[str, Any]],
    *,
    adapter: LLMAdapter | None = None,
) -> ClassificationResult:
    """
    Classify a cluster into topics using LLM.

    Convenience function that accepts data in database format.

    Args:
        cluster_title: The cluster's canonical title
        search_text: The cluster's search text (aggregated content)
        topics_from_db: List of topic dicts with 'name' and 'description_short'
        adapter: LLM adapter to use

    Returns:
        ClassificationResult with matched topics
    """
    available_topics = [
        TopicDefinition(
            name=t.get("name", ""),
            description=t.get("description_short"),
        )
        for t in topics_from_db
        if t.get("name")
    ]

    return classify_topics(
        title=cluster_title,
        content=search_text,
        available_topics=available_topics,
        adapter=adapter,
    )
