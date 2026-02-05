"""Update detection for story clusters.

This module detects when a story has meaningful new developments
and generates human-readable update summaries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


class UpdateType(str, Enum):
    """Types of story updates."""

    NEW_FINDINGS = "new_findings"
    REGULATORY = "regulatory"
    REPLICATION = "replication"
    APPLICATION = "application"
    CONTROVERSY = "controversy"
    FOLLOW_UP = "follow_up"
    NOT_MEANINGFUL = "not_meaningful"


@dataclass
class UpdateDetectionInput:
    """Input data for update detection."""

    existing_takeaway: str
    existing_deep_dive_summary: str | None
    new_article_title: str
    new_article_snippet: str
    new_article_source: str | None = None
    cluster_title: str | None = None
    days_since_last_update: int | None = None


@dataclass
class UpdateDetectionResult:
    """Result of update detection."""

    meaningful: bool
    update_type: UpdateType
    summary: str
    changes: list[str]
    confidence: float
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> UpdateDetectionResult:
        """Create a failure result."""
        return UpdateDetectionResult(
            meaningful=False,
            update_type=UpdateType.NOT_MEANINGFUL,
            summary="",
            changes=[],
            confidence=0.0,
            model="unknown",
            success=False,
            error=error,
        )

    @staticmethod
    def not_meaningful(model: str = "unknown") -> UpdateDetectionResult:
        """Create a non-meaningful result."""
        return UpdateDetectionResult(
            meaningful=False,
            update_type=UpdateType.NOT_MEANINGFUL,
            summary="",
            changes=[],
            confidence=0.9,
            model=model,
            success=True,
        )


UPDATE_DETECTION_SYSTEM_PROMPT = """You are analyzing science news updates to \
determine if a new article represents a meaningful development in an ongoing story.

A meaningful update includes:
- New research findings or data
- Regulatory decisions (FDA approvals, policy changes)
- Replication or contradiction of previous findings
- Real-world applications of research
- Scientific controversy or retractions
- Significant follow-up to previous research

NOT meaningful:
- Same story from a different source
- Minor rewording of existing information
- Opinion pieces without new facts
- Unrelated stories that mention similar topics"""


UPDATE_DETECTION_USER_PROMPT_TEMPLATE = """Compare this new article to the existing \
story and determine if it represents a meaningful update.

Existing Story Summary:
{existing_takeaway}

{deep_dive_section}

New Article:
Title: {new_article_title}
Source: {new_article_source}
Content: {new_article_snippet}

{time_context}

Respond with a JSON object:
{{
  "meaningful": true/false,
  "update_type": "new_findings|regulatory|replication|application|controversy|follow_up",
  "summary": "2-sentence summary of what changed (if meaningful)",
  "changes": ["change 1", "change 2"],
  "confidence": 0.0-1.0
}}

If NOT meaningful, respond:
{{
  "meaningful": false,
  "update_type": "not_meaningful",
  "summary": "",
  "changes": [],
  "confidence": 0.9
}}

Respond with ONLY the JSON object."""


def _format_deep_dive_section(summary: str | None) -> str:
    """Format deep-dive summary for prompt."""
    if not summary:
        return ""
    return f"\nExisting Deep-Dive Summary:\n{summary[:500]}\n"


def _format_time_context(days: int | None) -> str:
    """Format time context for prompt."""
    if days is None:
        return ""
    if days == 0:
        return "Time since last update: Same day"
    elif days == 1:
        return "Time since last update: Yesterday"
    elif days < 7:
        return f"Time since last update: {days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"Time since last update: {weeks} week(s) ago"
    else:
        months = days // 30
        return f"Time since last update: {months} month(s) ago"


def _parse_update_result(text: str) -> dict[str, Any] | None:
    """Parse update detection JSON from LLM response."""
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
        result = json.loads(text)
        return dict(result) if isinstance(result, dict) else None
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse update detection JSON: %s", e)
        return None


def detect_update(
    input_data: UpdateDetectionInput,
    *,
    adapter: LLMAdapter | None = None,
) -> UpdateDetectionResult:
    """
    Detect if a new article represents a meaningful update to a story.

    Args:
        input_data: The existing story and new article data
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        UpdateDetectionResult with detection results
    """
    if not input_data.existing_takeaway:
        return UpdateDetectionResult.failure("No existing takeaway provided")

    if not input_data.new_article_title:
        return UpdateDetectionResult.failure("No new article title provided")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    deep_dive_section = _format_deep_dive_section(input_data.existing_deep_dive_summary)
    time_context = _format_time_context(input_data.days_since_last_update)

    user_prompt = UPDATE_DETECTION_USER_PROMPT_TEMPLATE.format(
        existing_takeaway=input_data.existing_takeaway,
        deep_dive_section=deep_dive_section,
        new_article_title=input_data.new_article_title,
        new_article_source=input_data.new_article_source or "Unknown",
        new_article_snippet=input_data.new_article_snippet[:600],
        time_context=time_context,
    )

    # Try complete_json first for reliable JSON parsing
    raw_json = adapter.complete_json(
        user_prompt,
        system_prompt=UPDATE_DETECTION_SYSTEM_PROMPT,
        max_tokens=500,
    )

    # Get model name for result
    model_name = getattr(adapter, "model", adapter.name)

    if raw_json is None:
        # Fallback: try regular complete with manual parsing
        response: LLMResponse = adapter.complete(
            user_prompt,
            system_prompt=UPDATE_DETECTION_SYSTEM_PROMPT,
            max_tokens=500,
            temperature=0.3,
        )

        if not response.success:
            logger.warning("Update detection failed: %s", response.error)
            return UpdateDetectionResult.failure(response.error or "Unknown error")

        model_name = response.model
        raw_json = _parse_update_result(response.text)
        if raw_json is None:
            return UpdateDetectionResult.failure("Failed to parse JSON response")

    # Check if meaningful
    meaningful = bool(raw_json.get("meaningful", False))

    if not meaningful:
        return UpdateDetectionResult.not_meaningful(model_name)

    # Parse update type
    update_type_str = raw_json.get("update_type", "follow_up")
    try:
        update_type = UpdateType(update_type_str)
    except ValueError:
        update_type = UpdateType.FOLLOW_UP

    # Parse changes
    changes = raw_json.get("changes", [])
    if isinstance(changes, str):
        changes = [changes]
    elif not isinstance(changes, list):
        changes = []

    return UpdateDetectionResult(
        meaningful=True,
        update_type=update_type,
        summary=raw_json.get("summary", ""),
        changes=[str(c) for c in changes],
        confidence=float(raw_json.get("confidence", 0.7)),
        model=model_name,
        success=True,
    )


def detect_update_from_db_data(
    cluster_takeaway: str,
    cluster_deep_dive: str | None,
    new_item_title: str,
    new_item_snippet: str,
    new_item_source: str | None = None,
    cluster_title: str | None = None,
    cluster_updated_at: datetime | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> UpdateDetectionResult:
    """
    Detect update from database query results.

    Args:
        cluster_takeaway: Existing cluster takeaway
        cluster_deep_dive: Existing cluster deep-dive summary
        new_item_title: New article title
        new_item_snippet: New article snippet
        new_item_source: New article source name
        cluster_title: Cluster canonical title
        cluster_updated_at: When the cluster was last updated
        adapter: LLM adapter to use

    Returns:
        UpdateDetectionResult with detection results
    """
    days_since_update = None
    if cluster_updated_at:
        now = datetime.now(cluster_updated_at.tzinfo)
        days_since_update = (now - cluster_updated_at).days

    input_data = UpdateDetectionInput(
        existing_takeaway=cluster_takeaway,
        existing_deep_dive_summary=cluster_deep_dive,
        new_article_title=new_item_title,
        new_article_snippet=new_item_snippet,
        new_article_source=new_item_source,
        cluster_title=cluster_title,
        days_since_last_update=days_since_update,
    )

    return detect_update(input_data, adapter=adapter)


def update_result_to_json(result: UpdateDetectionResult) -> dict[str, Any]:
    """Convert UpdateDetectionResult to JSON-serializable dict."""
    return {
        "meaningful": result.meaningful,
        "update_type": result.update_type.value,
        "summary": result.summary,
        "changes": result.changes,
        "confidence": result.confidence,
    }
