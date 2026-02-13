"""Integration tests for AI takeaway generation.

These tests verify takeaway generation with real LLM backends.
Uses codex-cli as the primary test adapter.
"""

from __future__ import annotations

from typing import Any

import pytest

from curious_now.ai.llm_adapter import (
    ClaudeCLIAdapter,
    MockAdapter,
)
from curious_now.ai.takeaways import (
    MAX_TAKEAWAY_LENGTH,
    ItemSummary,
    TakeawayInput,
    TakeawayResult,
    _calculate_confidence,
    _format_articles,
    _format_topics,
    generate_takeaway,
    generate_takeaway_from_db_data,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test Data
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_crispr_items() -> list[ItemSummary]:
    """Sample items about CRISPR research."""
    return [
        ItemSummary(
            title="New CRISPR variant enables precise gene editing in neurons",
            snippet="Scientists at MIT have developed a modified version of CRISPR-Cas9 "
            "that can edit genes in brain cells with unprecedented precision, potentially "
            "opening new avenues for treating neurological diseases.",
            source_name="Nature",
            published_at="2026-02-01",
        ),
        ItemSummary(
            title="Gene therapy breakthrough offers hope for Huntington's patients",
            snippet="Researchers demonstrate that the new CRISPR technique can selectively "
            "target and disable the mutant huntingtin gene responsible for Huntington's "
            "disease in mouse models.",
            source_name="Science",
            published_at="2026-02-02",
        ),
        ItemSummary(
            title="Brain-targeted CRISPR advances to preclinical trials",
            snippet="Following successful lab results, the neuron-specific CRISPR system "
            "is now being prepared for preclinical safety trials, with researchers "
            "cautiously optimistic about its therapeutic potential.",
            source_name="STAT News",
            published_at="2026-02-03",
        ),
    ]


@pytest.fixture
def sample_climate_items() -> list[ItemSummary]:
    """Sample items about climate research."""
    return [
        ItemSummary(
            title="Antarctic ice sheet losing mass faster than predicted",
            snippet="New satellite data reveals Antarctic ice loss has accelerated by 40% "
            "compared to models from 2020, raising concerns about sea level rise projections.",
            source_name="Nature Climate Change",
            published_at="2026-02-01",
        ),
        ItemSummary(
            title="Updated climate models predict 2.5m sea level rise by 2100",
            snippet="Incorporating the latest Antarctic data, climate scientists have "
            "revised sea level projections upward, warning of significant impacts on "
            "coastal cities worldwide.",
            source_name="Science",
            published_at="2026-02-02",
        ),
    ]


@pytest.fixture
def sample_input(sample_crispr_items: list[ItemSummary]) -> TakeawayInput:
    """Complete sample input for takeaway generation."""
    return TakeawayInput(
        cluster_title="New CRISPR variant enables precise gene editing in neurons",
        items=sample_crispr_items,
        topic_names=["Gene Therapy", "Neuroscience", "CRISPR"],
    )


@pytest.fixture
def claude_adapter() -> ClaudeCLIAdapter:
    """Get Claude CLI adapter."""
    return ClaudeCLIAdapter()


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Get mock adapter for fast tests."""
    return MockAdapter(
        responses={
            "CRISPR": "A new CRISPR technique allows precise gene editing in brain cells, "
            "potentially enabling treatments for Huntington's and other neurological diseases "
            "that were previously impossible to address at the genetic level.",
            "Antarctic": "Antarctic ice is melting 40% faster than expected, suggesting sea "
            "levels may rise significantly higher than current projections by 2100.",
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatArticles:
    """Test article formatting helper."""

    def test_format_single_article(self) -> None:
        items = [
            ItemSummary(
                title="Test Article",
                snippet="This is a test snippet.",
                source_name="Test Source",
            )
        ]
        result = _format_articles(items)

        assert "1. Test Article" in result
        assert "Source: Test Source" in result
        assert "Summary: This is a test snippet." in result

    def test_format_multiple_articles(self) -> None:
        items = [
            ItemSummary(title="Article 1", snippet="Snippet 1"),
            ItemSummary(title="Article 2", snippet="Snippet 2"),
            ItemSummary(title="Article 3", snippet="Snippet 3"),
        ]
        result = _format_articles(items)

        assert "1. Article 1" in result
        assert "2. Article 2" in result
        assert "3. Article 3" in result

    def test_format_articles_limits_to_five(self) -> None:
        items = [ItemSummary(title=f"Article {i}") for i in range(10)]
        result = _format_articles(items)

        assert "5. Article 4" in result
        assert "6. Article 5" not in result

    def test_format_articles_truncates_long_snippets(self) -> None:
        long_snippet = "x" * 500
        items = [ItemSummary(title="Test", snippet=long_snippet)]
        result = _format_articles(items)

        # Should truncate to ~300 chars + "..."
        assert len(result) < len(long_snippet) + 50
        assert "..." in result

    def test_format_articles_handles_missing_fields(self) -> None:
        items = [ItemSummary(title="Just Title")]
        result = _format_articles(items)

        assert "1. Just Title" in result
        assert "Source:" not in result
        assert "Summary:" not in result


class TestFormatTopics:
    """Test topic formatting helper."""

    def test_format_topics(self) -> None:
        result = _format_topics(["AI", "Healthcare", "Research"])
        assert result == "Topics: AI, Healthcare, Research\n"

    def test_format_topics_empty(self) -> None:
        result = _format_topics([])
        assert result == ""

    def test_format_topics_none(self) -> None:
        result = _format_topics(None)
        assert result == ""


class TestCalculateConfidence:
    """Test confidence calculation."""

    def test_base_confidence(self, sample_input: TakeawayInput) -> None:
        takeaway = "A moderate length takeaway about an important discovery."
        confidence = _calculate_confidence(takeaway, sample_input)

        # Base is 0.8, with 3 items adds 0.1
        assert 0.8 <= confidence <= 1.0

    def test_short_takeaway_reduces_confidence(self, sample_input: TakeawayInput) -> None:
        short_takeaway = "Too short."
        confidence = _calculate_confidence(short_takeaway, sample_input)

        assert confidence < 0.8

    def test_single_item_reduces_confidence(self) -> None:
        input_data = TakeawayInput(
            cluster_title="Test",
            items=[ItemSummary(title="Single item")],
        )
        takeaway = "A moderate length takeaway about something."
        confidence = _calculate_confidence(takeaway, input_data)

        # Single item should reduce confidence
        assert confidence < 0.9

    def test_hype_words_reduce_confidence(self, sample_input: TakeawayInput) -> None:
        hype_takeaway = "This breakthrough cure is revolutionary!"
        normal_takeaway = "This finding shows promising results."

        hype_confidence = _calculate_confidence(hype_takeaway, sample_input)
        normal_confidence = _calculate_confidence(normal_takeaway, sample_input)

        assert hype_confidence < normal_confidence

    def test_confidence_bounded(self, sample_input: TakeawayInput) -> None:
        # Very short with hype words
        bad_takeaway = "Wow!"
        confidence = _calculate_confidence(bad_takeaway, sample_input)

        assert 0.0 <= confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Takeaway Generation with Mock
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateTakeawayMock:
    """Test takeaway generation with mock adapter."""

    def test_generate_takeaway_basic(
        self,
        sample_input: TakeawayInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_takeaway(sample_input, adapter=mock_adapter)

        assert isinstance(result, TakeawayResult)
        assert result.success is True
        assert len(result.takeaway) > 0
        assert result.model == "mock"

    def test_generate_takeaway_returns_confidence(
        self,
        sample_input: TakeawayInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_takeaway(sample_input, adapter=mock_adapter)

        assert 0.0 <= result.confidence <= 1.0

    def test_generate_takeaway_no_items_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = TakeawayInput(
            cluster_title="Test Cluster",
            items=[],
        )
        result = generate_takeaway(input_data, adapter=mock_adapter)

        assert result.success is False
        assert result.error is not None and "No items" in result.error

    def test_generate_takeaway_no_title_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = TakeawayInput(
            cluster_title="",
            items=[ItemSummary(title="Test")],
        )
        result = generate_takeaway(input_data, adapter=mock_adapter)

        assert result.success is False
        assert result.error is not None and "title" in result.error.lower()

    def test_generate_takeaway_strips_quotes(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        # Mock adapter wraps in quotes based on prompt
        adapter = MockAdapter(responses={"test": '"Quoted response"'})
        input_data = TakeawayInput(
            cluster_title="Test Cluster",
            items=[
                ItemSummary(
                    title="test article",
                    snippet=(
                        "This contains enough detail to pass the minimum content gate "
                        "for takeaway generation in tests."
                    ),
                )
            ],
        )
        result = generate_takeaway(input_data, adapter=adapter)

        assert result.success is True
        assert not result.takeaway.startswith('"')
        assert not result.takeaway.endswith('"')


class TestGenerateTakeawayFromDbData:
    """Test convenience function for DB data."""

    def test_generate_from_db_data(self, mock_adapter: MockAdapter) -> None:
        items: list[dict[str, Any]] = [
            {
                "title": "CRISPR advancement in neurons",
                "snippet": "Scientists develop new technique.",
                "source_name": "Nature",
                "published_at": "2026-02-01T00:00:00Z",
            },
            {
                "title": "Gene editing for brain diseases",
                "snippet": "Treatment possibilities expand.",
                "source_name": "Science",
                "published_at": None,
            },
        ]

        result = generate_takeaway_from_db_data(
            cluster_id="test-123",
            canonical_title="CRISPR enables neuron gene editing",
            items=items,
            topic_names=["CRISPR", "Neuroscience"],
            adapter=mock_adapter,
        )

        assert result.success is True
        assert len(result.takeaway) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests - Real LLM (Claude CLI)
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateTakeawayClaude:
    """Integration tests with real Claude CLI."""

    def test_claude_available(self, claude_adapter: ClaudeCLIAdapter) -> None:
        """Verify Claude CLI is available for testing."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")
        assert claude_adapter.is_available() is True

    def test_generate_crispr_takeaway(
        self,
        sample_input: TakeawayInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        """Test generating takeaway for CRISPR story."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_takeaway(sample_input, adapter=claude_adapter)

        assert result.success is True, f"Generation failed: {result.error}"
        assert len(result.takeaway) > 20, "Takeaway too short"
        assert len(result.takeaway) <= MAX_TAKEAWAY_LENGTH + 50, "Takeaway too long"

        # Check quality indicators
        takeaway_lower = result.takeaway.lower()
        # Should mention key concepts
        assert any(
            word in takeaway_lower
            for word in ["crispr", "gene", "brain", "neuron", "edit"]
        ), f"Takeaway missing key concepts: {result.takeaway}"

    def test_generate_climate_takeaway(
        self,
        sample_climate_items: list[ItemSummary],
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        """Test generating takeaway for climate story."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        input_data = TakeawayInput(
            cluster_title="Antarctic ice sheet losing mass faster than predicted",
            items=sample_climate_items,
            topic_names=["Climate Change", "Antarctica", "Sea Level"],
        )

        result = generate_takeaway(input_data, adapter=claude_adapter)

        assert result.success is True, f"Generation failed: {result.error}"
        assert len(result.takeaway) > 20

        takeaway_lower = result.takeaway.lower()
        assert any(
            word in takeaway_lower
            for word in ["ice", "antarctic", "sea", "climate", "melt"]
        ), f"Takeaway missing key concepts: {result.takeaway}"

    def test_takeaway_confidence_reasonable(
        self,
        sample_input: TakeawayInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        """Test that confidence score is reasonable."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_takeaway(sample_input, adapter=claude_adapter)

        assert result.success is True
        # With 3 items and reasonable length, confidence should be decent
        assert result.confidence >= 0.6, f"Confidence too low: {result.confidence}"

    def test_takeaway_no_hype(
        self,
        sample_input: TakeawayInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        """Test that takeaways avoid hype language."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_takeaway(sample_input, adapter=claude_adapter)

        assert result.success is True

        hype_words = ["breakthrough", "revolutionary", "game-changing", "miracle", "cure"]
        takeaway_lower = result.takeaway.lower()

        for word in hype_words:
            assert word not in takeaway_lower, (
                f"Takeaway contains hype word '{word}': {result.takeaway}"
            )

    def test_takeaway_with_single_item(
        self,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        """Test takeaway generation with minimal input."""
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        input_data = TakeawayInput(
            cluster_title="New quantum computer achieves 1000 qubit milestone",
            items=[
                ItemSummary(
                    title="IBM unveils 1000-qubit quantum processor",
                    snippet="IBM has announced its new Condor processor with over 1000 qubits, "
                    "marking a significant step toward practical quantum computing.",
                    source_name="IBM Research Blog",
                )
            ],
            topic_names=["Quantum Computing"],
        )

        result = generate_takeaway(input_data, adapter=claude_adapter)

        assert result.success is True
        assert len(result.takeaway) > 20
        # Confidence should be lower with single source
        assert result.confidence < 0.95


class TestTakeawayResultDataclass:
    """Test TakeawayResult dataclass."""

    def test_create_success_result(self) -> None:
        result = TakeawayResult(
            takeaway="Test takeaway",
            confidence=0.85,
            supporting_item_ids=["1", "2"],
            model="test-model",
            success=True,
        )

        assert result.takeaway == "Test takeaway"
        assert result.confidence == 0.85
        assert result.supporting_item_ids == ["1", "2"]
        assert result.success is True
        assert result.error is None

    def test_create_failure_result(self) -> None:
        result = TakeawayResult.failure("Something went wrong")

        assert result.takeaway == ""
        assert result.confidence == 0.0
        assert result.supporting_item_ids == []
        assert result.success is False
        assert result.error == "Something went wrong"
