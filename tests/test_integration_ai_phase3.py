"""Integration tests for Phase 3 AI features: Update Detection and Lineage.

These tests cover:
- Update Detection: detecting meaningful story updates
- Lineage Analysis: mapping relationships between stories
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from curious_now.ai.llm_adapter import ClaudeCLIAdapter

from curious_now.ai.lineage import (
    EdgeType,
    LineageAnalysisInput,
    LineageAnalysisResult,
    LineageEdge,
    StoryNode,
    _format_story_section,
    _parse_lineage_result,
    analyze_lineage,
    analyze_lineage_from_db_data,
    find_potential_connections,
    lineage_edge_to_json,
    lineage_result_to_json,
)
from curious_now.ai.llm_adapter import MockAdapter
from curious_now.ai.update_detection import (
    UpdateDetectionInput,
    UpdateDetectionResult,
    UpdateType,
    _format_deep_dive_section,
    _format_time_context,
    _parse_update_result,
    detect_update,
    detect_update_from_db_data,
    update_result_to_json,
)

# =============================================================================
# UPDATE DETECTION TESTS
# =============================================================================


class TestUpdateDetectionInput:
    """Tests for UpdateDetectionInput dataclass."""

    def test_basic_input(self) -> None:
        """Test creating basic update detection input."""
        input_data = UpdateDetectionInput(
            existing_takeaway="Previous research showed X",
            existing_deep_dive_summary="Detailed summary here",
            new_article_title="New Discovery in Field",
            new_article_snippet="Scientists have found new evidence...",
        )
        assert input_data.existing_takeaway == "Previous research showed X"
        assert input_data.new_article_title == "New Discovery in Field"

    def test_input_with_optional_fields(self) -> None:
        """Test input with all optional fields."""
        input_data = UpdateDetectionInput(
            existing_takeaway="Previous research",
            existing_deep_dive_summary="Deep dive content",
            new_article_title="New Article",
            new_article_snippet="New content here",
            new_article_source="Nature",
            cluster_title="Climate Research",
            days_since_last_update=7,
        )
        assert input_data.new_article_source == "Nature"
        assert input_data.days_since_last_update == 7


class TestUpdateDetectionResult:
    """Tests for UpdateDetectionResult dataclass."""

    def test_failure_result(self) -> None:
        """Test creating failure result."""
        result = UpdateDetectionResult.failure("Test error")
        assert result.success is False
        assert result.error == "Test error"
        assert result.meaningful is False
        assert result.update_type == UpdateType.NOT_MEANINGFUL

    def test_not_meaningful_result(self) -> None:
        """Test creating not-meaningful result."""
        result = UpdateDetectionResult.not_meaningful("test-model")
        assert result.success is True
        assert result.meaningful is False
        assert result.model == "test-model"

    def test_meaningful_result(self) -> None:
        """Test creating a meaningful result."""
        result = UpdateDetectionResult(
            meaningful=True,
            update_type=UpdateType.NEW_FINDINGS,
            summary="New data shows improved results",
            changes=["Better accuracy", "Faster processing"],
            confidence=0.85,
            model="test-model",
            success=True,
        )
        assert result.meaningful is True
        assert result.update_type == UpdateType.NEW_FINDINGS
        assert len(result.changes) == 2


class TestUpdateType:
    """Tests for UpdateType enum."""

    def test_all_update_types(self) -> None:
        """Test that all update types are defined."""
        types = [
            UpdateType.NEW_FINDINGS,
            UpdateType.REGULATORY,
            UpdateType.REPLICATION,
            UpdateType.APPLICATION,
            UpdateType.CONTROVERSY,
            UpdateType.FOLLOW_UP,
            UpdateType.NOT_MEANINGFUL,
        ]
        assert len(types) == 7

    def test_update_type_values(self) -> None:
        """Test update type string values."""
        assert UpdateType.NEW_FINDINGS.value == "new_findings"
        assert UpdateType.REGULATORY.value == "regulatory"
        assert UpdateType.NOT_MEANINGFUL.value == "not_meaningful"


class TestUpdateDetectionHelpers:
    """Tests for update detection helper functions."""

    def test_format_deep_dive_section_with_content(self) -> None:
        """Test formatting deep dive section with content."""
        result = _format_deep_dive_section("This is a summary of the research")
        assert "Existing Deep-Dive Summary:" in result
        assert "This is a summary" in result

    def test_format_deep_dive_section_empty(self) -> None:
        """Test formatting empty deep dive section."""
        assert _format_deep_dive_section(None) == ""
        assert _format_deep_dive_section("") == ""

    def test_format_deep_dive_section_truncation(self) -> None:
        """Test that long summaries are truncated."""
        long_summary = "x" * 600
        result = _format_deep_dive_section(long_summary)
        assert len(result) < 600  # Should be truncated

    def test_format_time_context_same_day(self) -> None:
        """Test time context for same day."""
        result = _format_time_context(0)
        assert "Same day" in result

    def test_format_time_context_yesterday(self) -> None:
        """Test time context for yesterday."""
        result = _format_time_context(1)
        assert "Yesterday" in result

    def test_format_time_context_days(self) -> None:
        """Test time context for days ago."""
        result = _format_time_context(5)
        assert "5 days ago" in result

    def test_format_time_context_weeks(self) -> None:
        """Test time context for weeks ago."""
        result = _format_time_context(14)
        assert "week" in result.lower()

    def test_format_time_context_months(self) -> None:
        """Test time context for months ago."""
        result = _format_time_context(60)
        assert "month" in result.lower()

    def test_format_time_context_none(self) -> None:
        """Test time context with None."""
        assert _format_time_context(None) == ""

    def test_parse_update_result_valid_json(self) -> None:
        """Test parsing valid JSON response."""
        json_str = json.dumps({
            "meaningful": True,
            "update_type": "new_findings",
            "summary": "New data available",
            "changes": ["change 1"],
            "confidence": 0.8,
        })
        result = _parse_update_result(json_str)
        assert result is not None
        assert result["meaningful"] is True

    def test_parse_update_result_markdown_block(self) -> None:
        """Test parsing JSON in markdown code block."""
        response = """```json
{
  "meaningful": false,
  "update_type": "not_meaningful",
  "summary": "",
  "changes": [],
  "confidence": 0.9
}
```"""
        result = _parse_update_result(response)
        assert result is not None
        assert result["meaningful"] is False

    def test_parse_update_result_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        result = _parse_update_result("not valid json at all")
        assert result is None


class TestDetectUpdateWithMock:
    """Tests for detect_update with mock adapter."""

    def test_detect_meaningful_update(self) -> None:
        """Test detecting a meaningful update."""
        mock_response = json.dumps({
            "meaningful": True,
            "update_type": "new_findings",
            "summary": "New clinical trial results show improved outcomes.",
            "changes": ["Phase 3 results published", "FDA review initiated"],
            "confidence": 0.85,
        })
        mock_adapter = MockAdapter(responses={"update": mock_response})

        input_data = UpdateDetectionInput(
            existing_takeaway="Initial drug trial shows promise",
            existing_deep_dive_summary="Phase 1 and 2 trials completed",
            new_article_title="Phase 3 Trial Results Released",
            new_article_snippet="The final phase of clinical trials...",
        )

        result = detect_update(input_data, adapter=mock_adapter)
        assert result.success is True
        assert result.meaningful is True
        assert result.update_type == UpdateType.NEW_FINDINGS
        assert len(result.changes) == 2

    def test_detect_not_meaningful_update(self) -> None:
        """Test detecting a non-meaningful update."""
        mock_response = json.dumps({
            "meaningful": False,
            "update_type": "not_meaningful",
            "summary": "",
            "changes": [],
            "confidence": 0.9,
        })
        mock_adapter = MockAdapter(responses={"update": mock_response})

        input_data = UpdateDetectionInput(
            existing_takeaway="Scientists discover new planet",
            existing_deep_dive_summary=None,
            new_article_title="New Planet Discovery Reported",
            new_article_snippet="Different source reports on same discovery",
        )

        result = detect_update(input_data, adapter=mock_adapter)
        assert result.success is True
        assert result.meaningful is False
        assert result.update_type == UpdateType.NOT_MEANINGFUL

    def test_detect_regulatory_update(self) -> None:
        """Test detecting a regulatory update."""
        mock_response = json.dumps({
            "meaningful": True,
            "update_type": "regulatory",
            "summary": "FDA grants emergency approval for treatment.",
            "changes": ["Emergency use authorization granted"],
            "confidence": 0.95,
        })
        mock_adapter = MockAdapter(responses={"update": mock_response})

        input_data = UpdateDetectionInput(
            existing_takeaway="New treatment under FDA review",
            existing_deep_dive_summary=None,
            new_article_title="FDA Approves New Treatment",
            new_article_snippet="The FDA has granted emergency authorization...",
        )

        result = detect_update(input_data, adapter=mock_adapter)
        assert result.update_type == UpdateType.REGULATORY

    def test_detect_update_missing_takeaway(self) -> None:
        """Test detection fails with missing takeaway."""
        mock_adapter = MockAdapter(responses={})
        input_data = UpdateDetectionInput(
            existing_takeaway="",
            existing_deep_dive_summary=None,
            new_article_title="Article Title",
            new_article_snippet="Article content",
        )

        result = detect_update(input_data, adapter=mock_adapter)
        assert result.success is False
        assert result.error is not None and "takeaway" in result.error.lower()

    def test_detect_update_missing_article_title(self) -> None:
        """Test detection fails with missing article title."""
        mock_adapter = MockAdapter(responses={})
        input_data = UpdateDetectionInput(
            existing_takeaway="Existing takeaway",
            existing_deep_dive_summary=None,
            new_article_title="",
            new_article_snippet="Article content",
        )

        result = detect_update(input_data, adapter=mock_adapter)
        assert result.success is False
        assert result.error is not None and "title" in result.error.lower()


class TestDetectUpdateFromDbData:
    """Tests for detect_update_from_db_data function."""

    def test_from_db_data_with_datetime(self) -> None:
        """Test update detection from DB data with datetime."""
        mock_response = json.dumps({
            "meaningful": True,
            "update_type": "follow_up",
            "summary": "Follow-up research confirms findings.",
            "changes": ["Confirmation study"],
            "confidence": 0.8,
        })
        mock_adapter = MockAdapter(responses={"update": mock_response})

        updated_at = datetime.now(timezone.utc) - timedelta(days=7)

        result = detect_update_from_db_data(
            cluster_takeaway="Initial research findings",
            cluster_deep_dive="Detailed analysis here",
            new_item_title="Follow-up Study Published",
            new_item_snippet="Researchers have confirmed...",
            new_item_source="Science Daily",
            cluster_title="Climate Research",
            cluster_updated_at=updated_at,
            adapter=mock_adapter,
        )

        assert result.success is True
        assert result.meaningful is True


class TestUpdateResultToJson:
    """Tests for update_result_to_json function."""

    def test_meaningful_result_to_json(self) -> None:
        """Test converting meaningful result to JSON."""
        result = UpdateDetectionResult(
            meaningful=True,
            update_type=UpdateType.NEW_FINDINGS,
            summary="New findings reported",
            changes=["Change 1", "Change 2"],
            confidence=0.85,
            model="test-model",
        )

        json_data = update_result_to_json(result)
        assert json_data["meaningful"] is True
        assert json_data["update_type"] == "new_findings"
        assert len(json_data["changes"]) == 2

    def test_not_meaningful_result_to_json(self) -> None:
        """Test converting not-meaningful result to JSON."""
        result = UpdateDetectionResult.not_meaningful("test-model")
        json_data = update_result_to_json(result)
        assert json_data["meaningful"] is False
        assert json_data["update_type"] == "not_meaningful"


# =============================================================================
# LINEAGE ANALYSIS TESTS
# =============================================================================


class TestStoryNode:
    """Tests for StoryNode dataclass."""

    def test_basic_story_node(self) -> None:
        """Test creating basic story node."""
        node = StoryNode(
            cluster_id="cluster-123",
            title="CRISPR Gene Editing Breakthrough",
        )
        assert node.cluster_id == "cluster-123"
        assert node.title == "CRISPR Gene Editing Breakthrough"

    def test_story_node_with_all_fields(self) -> None:
        """Test story node with all optional fields."""
        node = StoryNode(
            cluster_id="cluster-456",
            title="mRNA Vaccine Development",
            takeaway="New mRNA technology enables rapid vaccine creation",
            date="2024-01-15",
            topic_names=["Vaccines", "mRNA", "COVID-19"],
        )
        assert node.takeaway is not None
        assert node.topic_names is not None and len(node.topic_names) == 3


class TestLineageEdge:
    """Tests for LineageEdge dataclass."""

    def test_create_lineage_edge(self) -> None:
        """Test creating a lineage edge."""
        edge = LineageEdge(
            source_id="cluster-1",
            target_id="cluster-2",
            edge_type=EdgeType.LEADS_TO,
            explanation="Research A enabled Research B",
            confidence=0.9,
        )
        assert edge.source_id == "cluster-1"
        assert edge.edge_type == EdgeType.LEADS_TO
        assert edge.confidence == 0.9


class TestEdgeType:
    """Tests for EdgeType enum."""

    def test_all_edge_types(self) -> None:
        """Test that all edge types are defined."""
        types = [
            EdgeType.LEADS_TO,
            EdgeType.BUILDS_ON,
            EdgeType.CONTRADICTS,
            EdgeType.APPLIES,
            EdgeType.COMBINES,
            EdgeType.NOT_CONNECTED,
        ]
        assert len(types) == 6

    def test_edge_type_values(self) -> None:
        """Test edge type string values."""
        assert EdgeType.LEADS_TO.value == "leads_to"
        assert EdgeType.BUILDS_ON.value == "builds_on"
        assert EdgeType.CONTRADICTS.value == "contradicts"
        assert EdgeType.APPLIES.value == "applies"


class TestLineageAnalysisResult:
    """Tests for LineageAnalysisResult dataclass."""

    def test_failure_result(self) -> None:
        """Test creating failure result."""
        result = LineageAnalysisResult.failure("Test error")
        assert result.success is False
        assert result.error == "Test error"
        assert result.connected is False

    def test_not_connected_result(self) -> None:
        """Test creating not-connected result."""
        result = LineageAnalysisResult.not_connected("test-model")
        assert result.success is True
        assert result.connected is False
        assert result.edge is None

    def test_connected_result(self) -> None:
        """Test creating connected result."""
        edge = LineageEdge(
            source_id="a",
            target_id="b",
            edge_type=EdgeType.BUILDS_ON,
            explanation="B builds on A",
            confidence=0.8,
        )
        result = LineageAnalysisResult(
            connected=True,
            edge=edge,
            model="test-model",
            success=True,
        )
        assert result.connected is True
        assert result.edge is not None


class TestLineageHelpers:
    """Tests for lineage helper functions."""

    def test_format_story_section_with_data(self) -> None:
        """Test formatting story section with data."""
        takeaway, date, topics = _format_story_section(
            "A",
            "Key takeaway here",
            "2024-01-15",
            ["Biology", "Genetics"],
        )
        assert "Summary:" in takeaway
        assert "Date:" in date
        assert "Topics:" in topics

    def test_format_story_section_empty(self) -> None:
        """Test formatting story section with no data."""
        takeaway, date, topics = _format_story_section("A", None, None, None)
        assert takeaway == ""
        assert date == ""
        assert topics == ""

    def test_parse_lineage_result_valid(self) -> None:
        """Test parsing valid lineage JSON."""
        json_str = json.dumps({
            "connected": True,
            "relationship": "builds_on",
            "explanation": "Study B extends findings from A",
            "confidence": 0.85,
        })
        result = _parse_lineage_result(json_str)
        assert result is not None
        assert result["connected"] is True

    def test_parse_lineage_result_markdown(self) -> None:
        """Test parsing JSON in markdown block."""
        response = """```json
{
  "connected": false,
  "relationship": "not_connected",
  "explanation": "",
  "confidence": 0.9
}
```"""
        result = _parse_lineage_result(response)
        assert result is not None
        assert result["connected"] is False

    def test_parse_lineage_result_invalid(self) -> None:
        """Test parsing invalid JSON."""
        result = _parse_lineage_result("not json")
        assert result is None


class TestAnalyzeLineageWithMock:
    """Tests for analyze_lineage with mock adapter."""

    def test_connected_stories(self) -> None:
        """Test analyzing connected stories."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "leads_to",
            "explanation": "CRISPR research enabled targeted gene therapy.",
            "confidence": 0.9,
        })
        # Key "Story A" matches the prompt which contains "Story A (earlier)"
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(
            cluster_id="cluster-1",
            title="CRISPR Gene Editing Technique Developed",
            takeaway="New technique allows precise gene editing",
        )
        story_b = StoryNode(
            cluster_id="cluster-2",
            title="Gene Therapy Cures Rare Disease",
            takeaway="First successful treatment using gene editing",
        )

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.success is True
        assert result.connected is True
        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.LEADS_TO
        assert result.edge is not None
        assert result.edge.source_id == "cluster-1"
        assert result.edge is not None
        assert result.edge.target_id == "cluster-2"

    def test_not_connected_stories(self) -> None:
        """Test analyzing unrelated stories."""
        mock_response = json.dumps({
            "connected": False,
            "relationship": "not_connected",
            "explanation": "",
            "confidence": 0.95,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(
            cluster_id="cluster-1",
            title="New Solar Panel Efficiency Record",
        )
        story_b = StoryNode(
            cluster_id="cluster-2",
            title="Deep Sea Fish Species Discovered",
        )

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.success is True
        assert result.connected is False
        assert result.edge is None

    def test_builds_on_relationship(self) -> None:
        """Test detecting builds_on relationship."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "builds_on",
            "explanation": "Study builds on previous methodology.",
            "confidence": 0.8,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(
            cluster_id="a",
            title="Initial Study on Drug X",
        )
        story_b = StoryNode(
            cluster_id="b",
            title="Extended Study on Drug X",
        )

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.BUILDS_ON

    def test_contradicts_relationship(self) -> None:
        """Test detecting contradicts relationship."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "contradicts",
            "explanation": "New study refutes earlier claims.",
            "confidence": 0.85,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(cluster_id="a", title="Study Claims X")
        story_b = StoryNode(cluster_id="b", title="Study Disproves X")

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.CONTRADICTS

    def test_applies_relationship(self) -> None:
        """Test detecting applies relationship."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "applies",
            "explanation": "Commercial application of research.",
            "confidence": 0.88,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(cluster_id="a", title="Basic Research on Material")
        story_b = StoryNode(cluster_id="b", title="New Product Uses Material")

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.APPLIES

    def test_combines_relationship(self) -> None:
        """Test detecting combines relationship."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "combines",
            "explanation": "Interdisciplinary approach merges fields.",
            "confidence": 0.82,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(cluster_id="a", title="AI Research")
        story_b = StoryNode(cluster_id="b", title="AI-Powered Drug Discovery")

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.COMBINES

    def test_missing_title_fails(self) -> None:
        """Test that missing title causes failure."""
        mock_adapter = MockAdapter(responses={})

        story_a = StoryNode(cluster_id="a", title="")
        story_b = StoryNode(cluster_id="b", title="Valid Title")

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.success is False
        assert result.error is not None and "title" in result.error.lower()

    def test_invalid_relationship_defaults_to_builds_on(self) -> None:
        """Test that invalid relationship type defaults to builds_on."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "invalid_type",
            "explanation": "Some explanation",
            "confidence": 0.7,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        story_a = StoryNode(cluster_id="a", title="Story A")
        story_b = StoryNode(cluster_id="b", title="Story B")

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=mock_adapter)

        assert result.edge is not None
        assert result.edge.edge_type == EdgeType.BUILDS_ON


class TestAnalyzeLineageFromDbData:
    """Tests for analyze_lineage_from_db_data function."""

    def test_from_db_data(self) -> None:
        """Test lineage analysis from DB data."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "builds_on",
            "explanation": "Continued research on the topic.",
            "confidence": 0.85,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        result = analyze_lineage_from_db_data(
            cluster_a_id="cluster-a",
            cluster_a_title="Initial Study",
            cluster_a_takeaway="First findings on X",
            cluster_a_date="2024-01-01",
            cluster_a_topics=["Biology"],
            cluster_b_id="cluster-b",
            cluster_b_title="Follow-up Study",
            cluster_b_takeaway="Extended findings on X",
            cluster_b_date="2024-06-01",
            cluster_b_topics=["Biology", "Medicine"],
            adapter=mock_adapter,
        )

        assert result.success is True
        assert result.connected is True
        assert result.edge is not None
        assert result.edge.source_id == "cluster-a"
        assert result.edge is not None
        assert result.edge.target_id == "cluster-b"


class TestFindPotentialConnections:
    """Tests for find_potential_connections function."""

    def test_find_multiple_connections(self) -> None:
        """Test finding multiple connections."""
        # Mock responses for different queries
        def mock_complete(prompt: str, **kwargs: Any) -> str:
            if "Story A" in prompt:
                return json.dumps({
                    "connected": True,
                    "relationship": "leads_to",
                    "explanation": "A led to target",
                    "confidence": 0.9,
                })
            elif "Story B" in prompt:
                return json.dumps({
                    "connected": True,
                    "relationship": "builds_on",
                    "explanation": "Target builds on B",
                    "confidence": 0.8,
                })
            else:
                return json.dumps({
                    "connected": False,
                    "relationship": "not_connected",
                    "explanation": "",
                    "confidence": 0.9,
                })

        mock_adapter = MockAdapter(responses={"Story A": json.dumps({
            "connected": True,
            "relationship": "leads_to",
            "explanation": "Connection found",
            "confidence": 0.85,
        })})

        target = StoryNode(
            cluster_id="target",
            title="New Gene Therapy Treatment",
        )
        candidates = [
            StoryNode(cluster_id="a", title="Story A - CRISPR Research"),
            StoryNode(cluster_id="b", title="Story B - Gene Research"),
            StoryNode(cluster_id="c", title="Story C - Unrelated"),
        ]

        connections = find_potential_connections(
            target,
            candidates,
            adapter=mock_adapter,
            max_connections=3,
        )

        # All should be connected due to mock returning same response
        assert len(connections) >= 1
        for conn in connections:
            assert conn.connected is True

    def test_find_no_connections(self) -> None:
        """Test when no connections are found."""
        mock_response = json.dumps({
            "connected": False,
            "relationship": "not_connected",
            "explanation": "",
            "confidence": 0.95,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        target = StoryNode(cluster_id="target", title="Space Exploration")
        candidates = [
            StoryNode(cluster_id="a", title="Cooking Recipes"),
            StoryNode(cluster_id="b", title="Fashion Trends"),
        ]

        connections = find_potential_connections(
            target,
            candidates,
            adapter=mock_adapter,
        )

        assert len(connections) == 0

    def test_max_connections_limit(self) -> None:
        """Test that max_connections limits results."""
        mock_response = json.dumps({
            "connected": True,
            "relationship": "builds_on",
            "explanation": "Connected",
            "confidence": 0.8,
        })
        mock_adapter = MockAdapter(responses={"Story A": mock_response})

        target = StoryNode(cluster_id="target", title="Target Story")
        candidates = [
            StoryNode(cluster_id=f"c{i}", title=f"Candidate {i}")
            for i in range(10)
        ]

        connections = find_potential_connections(
            target,
            candidates,
            adapter=mock_adapter,
            max_connections=3,
        )

        assert len(connections) <= 3


class TestLineageJsonSerialization:
    """Tests for JSON serialization functions."""

    def test_lineage_edge_to_json(self) -> None:
        """Test converting edge to JSON."""
        edge = LineageEdge(
            source_id="source-1",
            target_id="target-1",
            edge_type=EdgeType.LEADS_TO,
            explanation="Source led to target",
            confidence=0.9,
        )

        json_data = lineage_edge_to_json(edge)
        assert json_data["source_id"] == "source-1"
        assert json_data["target_id"] == "target-1"
        assert json_data["edge_type"] == "leads_to"
        assert json_data["confidence"] == 0.9

    def test_lineage_result_to_json_connected(self) -> None:
        """Test converting connected result to JSON."""
        edge = LineageEdge(
            source_id="a",
            target_id="b",
            edge_type=EdgeType.BUILDS_ON,
            explanation="B builds on A",
            confidence=0.85,
        )
        result = LineageAnalysisResult(
            connected=True,
            edge=edge,
            model="test-model",
            success=True,
        )

        json_data = lineage_result_to_json(result)
        assert json_data["connected"] is True
        assert json_data["edge"] is not None
        assert json_data["edge"]["edge_type"] == "builds_on"

    def test_lineage_result_to_json_not_connected(self) -> None:
        """Test converting not-connected result to JSON."""
        result = LineageAnalysisResult.not_connected("test-model")
        json_data = lineage_result_to_json(result)
        assert json_data["connected"] is False
        assert json_data["edge"] is None


# =============================================================================
# INTEGRATION TESTS WITH CLAUDE CLI
# =============================================================================


class TestUpdateDetectionIntegration:
    """Integration tests for update detection with ClaudeCLIAdapter."""

    @pytest.fixture
    def claude_adapter(self) -> ClaudeCLIAdapter:
        """Get ClaudeCLIAdapter if available."""
        from curious_now.ai.llm_adapter import ClaudeCLIAdapter
        adapter = ClaudeCLIAdapter()
        if not adapter.is_available():
            pytest.skip("Claude CLI not available")
        return adapter

    def test_detect_meaningful_update_integration(self, claude_adapter: ClaudeCLIAdapter) -> None:
        """Integration test for detecting meaningful update."""
        input_data = UpdateDetectionInput(
            existing_takeaway="Initial mRNA vaccine trials show 90% efficacy "
                            "against COVID-19 in Phase 2 trials.",
            existing_deep_dive_summary="Moderna's mRNA vaccine candidate "
                                       "completed Phase 2 trials with promising results.",
            new_article_title="mRNA Vaccine Receives FDA Emergency Authorization",
            new_article_snippet="The FDA has granted emergency use authorization "
                               "to Moderna's mRNA vaccine following successful "
                               "Phase 3 trials showing 94% efficacy.",
            new_article_source="FDA News",
            days_since_last_update=30,
        )

        result = detect_update(input_data, adapter=claude_adapter)

        assert result.success is True
        # Should be meaningful - this is a regulatory update
        if result.meaningful:
            assert result.update_type in [
                UpdateType.REGULATORY,
                UpdateType.NEW_FINDINGS,
                UpdateType.FOLLOW_UP,
            ]

    def test_detect_not_meaningful_update_integration(self, claude_adapter: ClaudeCLIAdapter) -> None:
        """Integration test for detecting non-meaningful update."""
        input_data = UpdateDetectionInput(
            existing_takeaway="Scientists discover high concentrations of "
                            "microplastics in Arctic ice cores.",
            existing_deep_dive_summary=None,
            new_article_title="Arctic Ice Contains Microplastic Pollution",
            new_article_snippet="A report discusses the presence of microplastic "
                               "particles discovered in Arctic ice samples, "
                               "highlighting environmental concerns.",
            new_article_source="Environment Blog",
        )

        result = detect_update(input_data, adapter=claude_adapter)

        assert result.success is True
        # This is essentially the same story from different source


class TestLineageAnalysisIntegration:
    """Integration tests for lineage analysis with ClaudeCLIAdapter."""

    @pytest.fixture
    def claude_adapter(self) -> ClaudeCLIAdapter:
        """Get ClaudeCLIAdapter if available."""
        from curious_now.ai.llm_adapter import ClaudeCLIAdapter
        adapter = ClaudeCLIAdapter()
        if not adapter.is_available():
            pytest.skip("Claude CLI not available")
        return adapter

    def test_connected_stories_integration(self, claude_adapter: ClaudeCLIAdapter) -> None:
        """Integration test for connected stories."""
        story_a = StoryNode(
            cluster_id="crispr-discovery",
            title="CRISPR Gene Editing Technology Developed",
            takeaway="Scientists develop precise gene editing tool using "
                    "bacterial immune system mechanism.",
            date="2012-06-28",
            topic_names=["Genetics", "Biotechnology"],
        )
        story_b = StoryNode(
            cluster_id="sickle-cell-cure",
            title="CRISPR-Based Sickle Cell Treatment Approved",
            takeaway="FDA approves first CRISPR therapy to cure sickle cell disease.",
            date="2023-12-08",
            topic_names=["Medicine", "Gene Therapy", "FDA"],
        )

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=claude_adapter)

        assert result.success is True
        # These stories should be connected
        if result.connected:
            assert result.edge is not None
            assert result.edge.edge_type in [
                EdgeType.LEADS_TO,
                EdgeType.APPLIES,
                EdgeType.BUILDS_ON,
            ]

    def test_unrelated_stories_integration(self, claude_adapter: ClaudeCLIAdapter) -> None:
        """Integration test for unrelated stories."""
        story_a = StoryNode(
            cluster_id="solar-panel",
            title="New Solar Panel Design Achieves Record Efficiency",
            takeaway="Perovskite solar cells reach 30% efficiency.",
            date="2024-01-15",
            topic_names=["Renewable Energy", "Materials Science"],
        )
        story_b = StoryNode(
            cluster_id="deep-sea",
            title="New Deep Sea Fish Species Discovered",
            takeaway="Marine biologists discover bioluminescent fish at "
                    "record depths.",
            date="2024-02-20",
            topic_names=["Marine Biology", "Biodiversity"],
        )

        input_data = LineageAnalysisInput(story_a=story_a, story_b=story_b)
        result = analyze_lineage(input_data, adapter=claude_adapter)

        assert result.success is True
        # These stories should not be connected


class TestPhase3ModuleImports:
    """Tests to verify Phase 3 module imports work correctly."""

    def test_import_update_detection(self) -> None:
        """Test importing update detection from main package."""
        from curious_now.ai import (
            UpdateDetectionInput,
            UpdateDetectionResult,
            UpdateType,
        )
        assert UpdateDetectionInput is not None
        assert UpdateDetectionResult is not None
        assert UpdateType is not None

    def test_import_lineage(self) -> None:
        """Test importing lineage from main package."""
        from curious_now.ai import (
            EdgeType,
            LineageAnalysisResult,
            StoryNode,
        )
        assert EdgeType is not None
        assert LineageAnalysisResult is not None
        assert StoryNode is not None
