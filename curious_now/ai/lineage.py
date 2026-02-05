"""Story lineage mapping for story clusters.

This module maps how scientific topics connect and evolve over time,
creating a knowledge graph of scientific progress.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


class EdgeType(str, Enum):
    """Types of lineage relationships between stories."""

    LEADS_TO = "leads_to"  # Research A enabled Research B
    BUILDS_ON = "builds_on"  # Incremental progress
    CONTRADICTS = "contradicts"  # Conflicting findings
    APPLIES = "applies"  # Basic research → Application
    COMBINES = "combines"  # Multiple fields merge
    NOT_CONNECTED = "not_connected"


@dataclass
class StoryNode:
    """A story node for lineage analysis."""

    cluster_id: str
    title: str
    takeaway: str | None = None
    date: str | None = None
    topic_names: list[str] | None = None


@dataclass
class LineageEdge:
    """A relationship edge between two stories."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    explanation: str
    confidence: float


@dataclass
class LineageAnalysisInput:
    """Input data for lineage analysis."""

    story_a: StoryNode  # Earlier story
    story_b: StoryNode  # Later story


@dataclass
class LineageAnalysisResult:
    """Result of lineage analysis between two stories."""

    connected: bool
    edge: LineageEdge | None
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> LineageAnalysisResult:
        """Create a failure result."""
        return LineageAnalysisResult(
            connected=False,
            edge=None,
            model="unknown",
            success=False,
            error=error,
        )

    @staticmethod
    def not_connected(model: str = "unknown") -> LineageAnalysisResult:
        """Create a not-connected result."""
        return LineageAnalysisResult(
            connected=False,
            edge=None,
            model=model,
            success=True,
        )


LINEAGE_SYSTEM_PROMPT = """You are a science historian analyzing how scientific \
discoveries and stories connect over time.

Relationship types:
- leads_to: Story A directly enabled or led to Story B
- builds_on: Story B is incremental progress from Story A
- contradicts: Story B challenges or refutes findings in Story A
- applies: Story B is a real-world application of research in Story A
- combines: Story B combines concepts from Story A with other fields

Only identify connections when there's a clear scientific relationship.
Don't connect stories just because they're in the same general field."""


LINEAGE_USER_PROMPT_TEMPLATE = """Analyze if these two science stories are connected.

Story A (earlier):
Title: {title_a}
{takeaway_a}
{date_a}
{topics_a}

Story B (later):
Title: {title_b}
{takeaway_b}
{date_b}
{topics_b}

Are these stories meaningfully connected in terms of scientific progress?

Respond with a JSON object:
{{
  "connected": true/false,
  "relationship": "leads_to|builds_on|contradicts|applies|combines",
  "explanation": "One sentence explaining the connection",
  "confidence": 0.0-1.0
}}

If NOT connected:
{{
  "connected": false,
  "relationship": "not_connected",
  "explanation": "",
  "confidence": 0.9
}}

Respond with ONLY the JSON object."""


def _format_story_section(
    prefix: str,
    takeaway: str | None,
    date: str | None,
    topics: list[str] | None,
) -> tuple[str, str, str]:
    """Format story sections for the prompt."""
    takeaway_str = f"Summary: {takeaway}" if takeaway else ""
    date_str = f"Date: {date}" if date else ""
    topics_str = f"Topics: {', '.join(topics)}" if topics else ""
    return takeaway_str, date_str, topics_str


def _parse_lineage_result(text: str) -> dict[str, Any] | None:
    """Parse lineage analysis JSON from LLM response."""
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
        logger.warning("Failed to parse lineage JSON: %s", e)
        return None


def analyze_lineage(
    input_data: LineageAnalysisInput,
    *,
    adapter: LLMAdapter | None = None,
) -> LineageAnalysisResult:
    """
    Analyze the relationship between two stories.

    Args:
        input_data: The two stories to analyze
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        LineageAnalysisResult with relationship details
    """
    story_a = input_data.story_a
    story_b = input_data.story_b

    if not story_a.title or not story_b.title:
        return LineageAnalysisResult.failure("Both stories must have titles")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    takeaway_a, date_a, topics_a = _format_story_section(
        "A", story_a.takeaway, story_a.date, story_a.topic_names
    )
    takeaway_b, date_b, topics_b = _format_story_section(
        "B", story_b.takeaway, story_b.date, story_b.topic_names
    )

    user_prompt = LINEAGE_USER_PROMPT_TEMPLATE.format(
        title_a=story_a.title,
        takeaway_a=takeaway_a,
        date_a=date_a,
        topics_a=topics_a,
        title_b=story_b.title,
        takeaway_b=takeaway_b,
        date_b=date_b,
        topics_b=topics_b,
    )

    # Try complete_json first for reliable JSON parsing
    raw_json = adapter.complete_json(
        user_prompt,
        system_prompt=LINEAGE_SYSTEM_PROMPT,
        max_tokens=300,
    )

    # Get model name for result
    model_name = getattr(adapter, "model", adapter.name)

    if raw_json is None:
        # Fallback: try regular complete with manual parsing
        response: LLMResponse = adapter.complete(
            user_prompt,
            system_prompt=LINEAGE_SYSTEM_PROMPT,
            max_tokens=300,
            temperature=0.3,
        )

        if not response.success:
            logger.warning("Lineage analysis failed: %s", response.error)
            return LineageAnalysisResult.failure(response.error or "Unknown error")

        model_name = response.model
        raw_json = _parse_lineage_result(response.text)
        if raw_json is None:
            return LineageAnalysisResult.failure("Failed to parse JSON response")

    # Check if connected
    connected = bool(raw_json.get("connected", False))

    if not connected:
        return LineageAnalysisResult.not_connected(model_name)

    # Parse relationship type
    relationship_str = raw_json.get("relationship", "builds_on")
    try:
        edge_type = EdgeType(relationship_str)
    except ValueError:
        edge_type = EdgeType.BUILDS_ON

    # Create edge
    edge = LineageEdge(
        source_id=story_a.cluster_id,
        target_id=story_b.cluster_id,
        edge_type=edge_type,
        explanation=raw_json.get("explanation", ""),
        confidence=float(raw_json.get("confidence", 0.7)),
    )

    return LineageAnalysisResult(
        connected=True,
        edge=edge,
        model=model_name,
        success=True,
    )


def analyze_lineage_from_db_data(
    cluster_a_id: str,
    cluster_a_title: str,
    cluster_a_takeaway: str | None,
    cluster_a_date: str | None,
    cluster_a_topics: list[str] | None,
    cluster_b_id: str,
    cluster_b_title: str,
    cluster_b_takeaway: str | None,
    cluster_b_date: str | None,
    cluster_b_topics: list[str] | None,
    *,
    adapter: LLMAdapter | None = None,
) -> LineageAnalysisResult:
    """
    Analyze lineage from database query results.

    Args:
        cluster_a_*: Earlier cluster data
        cluster_b_*: Later cluster data
        adapter: LLM adapter to use

    Returns:
        LineageAnalysisResult with relationship details
    """
    story_a = StoryNode(
        cluster_id=cluster_a_id,
        title=cluster_a_title,
        takeaway=cluster_a_takeaway,
        date=cluster_a_date,
        topic_names=cluster_a_topics,
    )
    story_b = StoryNode(
        cluster_id=cluster_b_id,
        title=cluster_b_title,
        takeaway=cluster_b_takeaway,
        date=cluster_b_date,
        topic_names=cluster_b_topics,
    )

    input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
    return analyze_lineage(input_data, adapter=adapter)


def find_potential_connections(
    target_cluster: StoryNode,
    candidate_clusters: list[StoryNode],
    *,
    adapter: LLMAdapter | None = None,
    max_connections: int = 5,
) -> list[LineageAnalysisResult]:
    """
    Find potential lineage connections for a new cluster.

    Analyzes the target cluster against multiple candidate clusters
    to find meaningful connections.

    Args:
        target_cluster: The new cluster to find connections for
        candidate_clusters: List of potential predecessor clusters
        adapter: LLM adapter to use
        max_connections: Maximum number of connections to return

    Returns:
        List of LineageAnalysisResult for connected stories
    """
    if adapter is None:
        adapter = get_llm_adapter()

    connections = []

    for candidate in candidate_clusters:
        input_data = LineageAnalysisInput(story_a=candidate, story_b=target_cluster)
        result = analyze_lineage(input_data, adapter=adapter)

        if result.success and result.connected:
            connections.append(result)

            if len(connections) >= max_connections:
                break

    # Sort by confidence
    connections.sort(key=lambda r: r.edge.confidence if r.edge else 0, reverse=True)

    return connections[:max_connections]


def lineage_edge_to_json(edge: LineageEdge) -> dict[str, Any]:
    """Convert LineageEdge to JSON-serializable dict."""
    return {
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "edge_type": edge.edge_type.value,
        "explanation": edge.explanation,
        "confidence": edge.confidence,
    }


def lineage_result_to_json(result: LineageAnalysisResult) -> dict[str, Any]:
    """Convert LineageAnalysisResult to JSON-serializable dict."""
    return {
        "connected": result.connected,
        "edge": lineage_edge_to_json(result.edge) if result.edge else None,
        "success": result.success,
        "error": result.error,
    }
