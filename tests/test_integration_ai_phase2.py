"""Integration tests for Phase 2 AI features.

Tests for:
- Intuition generation
- Deep-dive content generation
- Citation validation

Uses Claude CLI for integration tests.
"""

from __future__ import annotations

import pytest

from curious_now.ai.citation_check import (
    CheckedClaim,
    CitationCheckInput,
    CitationCheckResult,
    CitationFlag,
    FlagType,
    SourceText,
    check_citations,
    check_takeaway_citations,
)
from curious_now.ai.deep_dive import (
    DeepDiveContent,
    DeepDiveInput,
    DeepDiveResult,
    SourceSummary,
    deep_dive_from_json,
    deep_dive_to_json,
    generate_deep_dive,
)
from curious_now.ai.intuition import (
    GlossaryTerm,
    IntuitionInput,
    IntuitionResult,
    _extract_analogies,
    generate_intuition,
)
from curious_now.ai.intuition import (
    _calculate_confidence as calculate_intuition_confidence,
)
from curious_now.ai.llm_adapter import ClaudeCLIAdapter, MockAdapter

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def claude_adapter() -> ClaudeCLIAdapter:
    """Get Claude CLI adapter."""
    return ClaudeCLIAdapter()


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Get mock adapter for fast tests.

    Keys are chosen to match text that appears in the actual prompts.
    """
    return MockAdapter(
        responses={
            # Matches "analogy" in intuition prompts
            "analogy": "CRISPR works like molecular scissors that can cut DNA at "
            "precise locations. The new variant is like having steadier hands for "
            "brain surgery - crucial because neurons don't regenerate. "
            "[Analogies: scissors, surgery]",
            # Matches "deep-dive" in deep_dive prompts
            "deep-dive": """{
                "what_happened": "Scientists developed a modified CRISPR system.",
                "why_it_matters": "This enables gene therapy in brain cells.",
                "background": "CRISPR has been used in other tissues since 2012.",
                "limitations": ["Only tested in mice", "High cost", "Limited availability"],
                "whats_next": "Clinical trials expected within 3 years.",
                "related_concepts": ["gene therapy", "Cas9", "neurons"]
            }""",
            # Matches "Validate" in citation check prompts
            "validate": """{
                "validated": true,
                "overall_confidence": 0.9,
                "claims": [
                    {
                        "claim": "CRISPR works in neurons",
                        "supported": true,
                        "source": "Nature",
                        "confidence": 0.95
                    }
                ],
                "flags": []
            }""",
        }
    )


@pytest.fixture
def sample_intuition_input() -> IntuitionInput:
    """Sample input for intuition generation."""
    return IntuitionInput(
        cluster_title="New CRISPR variant enables precise gene editing in neurons",
        takeaway="Scientists developed a CRISPR modification that works in brain cells, "
        "potentially enabling treatments for neurological diseases.",
        technical_snippets=[
            "The modified Cas9 enzyme shows reduced off-target effects in post-mitotic cells "
            "due to enhanced PAM specificity.",
            "Delivery was achieved using AAV9 vectors with neuron-specific promoters.",
        ],
        glossary_terms=[
            GlossaryTerm(term="CRISPR", definition="Gene editing technology"),
            GlossaryTerm(term="Cas9", definition="The enzyme that cuts DNA"),
        ],
        topic_names=["Gene Therapy", "Neuroscience"],
    )


@pytest.fixture
def sample_deep_dive_input() -> DeepDiveInput:
    """Sample input for deep-dive generation."""
    return DeepDiveInput(
        cluster_title="FDA approves first CRISPR-based therapy",
        takeaway="The FDA approved Casgevy for sickle cell disease, marking a historic milestone.",
        source_summaries=[
            SourceSummary(
                title="FDA Approves First CRISPR Therapy for Sickle Cell Disease",
                snippet=(
                    "The FDA has approved Casgevy, developed by Vertex and CRISPR "
                    "Therapeutics, for treating sickle cell disease in patients 12+."
                ),
                source_name="FDA Press Release",
                source_type="government",
            ),
            SourceSummary(
                title="CRISPR gene therapy receives landmark FDA approval",
                snippet="The approval marks the first time a CRISPR-based therapy has been "
                "authorized for use in the United States.",
                source_name="Nature",
                source_type="journal",
            ),
            SourceSummary(
                title="What the first CRISPR therapy approval means for patients",
                snippet="The treatment costs approximately $2.2 million and requires "
                "hospitalization for bone marrow extraction.",
                source_name="STAT News",
                source_type="journalism",
            ),
        ],
        glossary_terms=["CRISPR", "sickle cell disease", "gene therapy"],
        topic_names=["Gene Therapy", "FDA", "Rare Diseases"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Intuition Tests - Unit
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractAnalogies:
    """Test analogy extraction from response text."""

    def test_extract_analogies_standard_format(self) -> None:
        text = "CRISPR is like scissors. [Analogies: scissors, lock and key]"
        clean, analogies = _extract_analogies(text)

        assert clean == "CRISPR is like scissors."
        assert analogies == ["scissors", "lock and key"]

    def test_extract_analogies_singular(self) -> None:
        text = "It works like a key. [Analogy: key]"
        clean, analogies = _extract_analogies(text)

        assert clean == "It works like a key."
        assert analogies == ["key"]

    def test_extract_analogies_none(self) -> None:
        text = "This is an explanation without analogies."
        clean, analogies = _extract_analogies(text)

        assert clean == text
        assert analogies == []


class TestCalculateIntuitionConfidence:
    """Test intuition confidence calculation."""

    def test_good_length_increases_confidence(
        self, sample_intuition_input: IntuitionInput
    ) -> None:
        good_intuition = " ".join(["word"] * 100)  # 100 words
        confidence = calculate_intuition_confidence(good_intuition, sample_intuition_input)

        assert confidence > 0.8

    def test_jargon_reduces_confidence(
        self, sample_intuition_input: IntuitionInput
    ) -> None:
        jargon_intuition = "The methodology paradigm shows statistically significant results."
        confidence = calculate_intuition_confidence(jargon_intuition, sample_intuition_input)

        # Should be lower due to jargon
        assert confidence < 0.8


class TestGenerateIntuitionMock:
    """Test intuition generation with mock adapter."""

    def test_generate_intuition_basic(
        self,
        sample_intuition_input: IntuitionInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_intuition(sample_intuition_input, adapter=mock_adapter)

        assert isinstance(result, IntuitionResult)
        assert result.success is True
        assert len(result.intuition) > 0

    def test_generate_intuition_extracts_analogies(
        self,
        sample_intuition_input: IntuitionInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_intuition(sample_intuition_input, adapter=mock_adapter)

        assert result.success is True
        assert len(result.analogies_used) > 0

    def test_generate_intuition_no_title_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = IntuitionInput(cluster_title="")
        result = generate_intuition(input_data, adapter=mock_adapter)

        assert result.success is False
        assert "title" in result.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Intuition Tests - Integration (Claude CLI)
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateIntuitionClaude:
    """Integration tests for intuition generation with Claude CLI."""

    def test_generate_crispr_intuition(
        self,
        sample_intuition_input: IntuitionInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_intuition(sample_intuition_input, adapter=claude_adapter)

        assert result.success is True, f"Generation failed: {result.error}"
        assert len(result.intuition) > 50
        assert result.confidence > 0.5

    def test_intuition_uses_simple_language(
        self,
        sample_intuition_input: IntuitionInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_intuition(sample_intuition_input, adapter=claude_adapter)

        assert result.success is True

        # Should avoid heavy jargon
        jargon_words = ["methodology", "paradigm", "pursuant"]
        intuition_lower = result.intuition.lower()
        for word in jargon_words:
            assert word not in intuition_lower, (
                f"Intuition contains jargon '{word}': {result.intuition}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Deep Dive Tests - Unit
# ─────────────────────────────────────────────────────────────────────────────


class TestDeepDiveContent:
    """Test DeepDiveContent dataclass."""

    def test_deep_dive_to_json(self) -> None:
        content = DeepDiveContent(
            what_happened="Test happened",
            why_it_matters="It matters because...",
            background="Background info",
            limitations=["Limit 1", "Limit 2"],
            whats_next="Next steps",
            related_concepts=["concept1", "concept2"],
            generated_at="2026-02-05T10:00:00Z",
            source_count=3,
        )

        json_data = deep_dive_to_json(content)

        assert json_data["what_happened"] == "Test happened"
        assert len(json_data["limitations"]) == 2
        assert json_data["source_count"] == 3

    def test_deep_dive_from_json(self) -> None:
        json_data = {
            "what_happened": "Test happened",
            "why_it_matters": "It matters",
            "background": "Background",
            "limitations": ["Limit 1"],
            "whats_next": "Next",
            "related_concepts": [],
            "generated_at": "2026-02-05T10:00:00Z",
            "source_count": 2,
        }

        content = deep_dive_from_json(json_data)

        assert content is not None
        assert content.what_happened == "Test happened"

    def test_deep_dive_from_json_invalid(self) -> None:
        json_data = {"incomplete": "data"}

        content = deep_dive_from_json(json_data)

        assert content is None


class TestGenerateDeepDiveMock:
    """Test deep-dive generation with mock adapter."""

    def test_generate_deep_dive_basic(
        self,
        sample_deep_dive_input: DeepDiveInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_deep_dive(sample_deep_dive_input, adapter=mock_adapter)

        assert isinstance(result, DeepDiveResult)
        assert result.success is True
        assert result.content is not None

    def test_generate_deep_dive_has_all_sections(
        self,
        sample_deep_dive_input: DeepDiveInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_deep_dive(sample_deep_dive_input, adapter=mock_adapter)

        assert result.success is True
        assert result.content.what_happened
        assert result.content.why_it_matters
        assert result.content.background
        assert result.content.whats_next
        assert len(result.content.limitations) > 0

    def test_generate_deep_dive_no_title_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = DeepDiveInput(cluster_title="")
        result = generate_deep_dive(input_data, adapter=mock_adapter)

        assert result.success is False


# ─────────────────────────────────────────────────────────────────────────────
# Deep Dive Tests - Integration (Claude CLI)
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateDeepDiveClaude:
    """Integration tests for deep-dive generation with Claude CLI."""

    def test_generate_fda_approval_deep_dive(
        self,
        sample_deep_dive_input: DeepDiveInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_deep_dive(sample_deep_dive_input, adapter=claude_adapter)

        assert result.success is True, f"Generation failed: {result.error}"
        assert result.content is not None

        # Check all sections have content
        assert len(result.content.what_happened) > 20
        assert len(result.content.why_it_matters) > 20
        assert len(result.content.background) > 20
        assert len(result.content.whats_next) > 20

    def test_deep_dive_includes_limitations(
        self,
        sample_deep_dive_input: DeepDiveInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_deep_dive(sample_deep_dive_input, adapter=claude_adapter)

        assert result.success is True
        assert len(result.content.limitations) >= 1

    def test_deep_dive_confidence_reasonable(
        self,
        sample_deep_dive_input: DeepDiveInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_deep_dive(sample_deep_dive_input, adapter=claude_adapter)

        assert result.success is True
        # With 3 sources and structured content, confidence should be decent
        assert result.confidence >= 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Citation Check Tests - Unit
# ─────────────────────────────────────────────────────────────────────────────


class TestCitationCheckDataclasses:
    """Test citation check dataclasses."""

    def test_citation_flag_creation(self) -> None:
        flag = CitationFlag(
            flag_type=FlagType.OVERSTATEMENT,
            claim="This cures all diseases",
            issue="Source only mentions one disease",
            suggestion="Specify sickle cell only",
        )

        assert flag.flag_type == FlagType.OVERSTATEMENT
        assert "cures" in flag.claim

    def test_checked_claim_creation(self) -> None:
        claim = CheckedClaim(
            claim="FDA approved the therapy",
            supported=True,
            source="FDA Press Release",
            confidence=0.95,
        )

        assert claim.supported is True
        assert claim.confidence == 0.95

    def test_citation_check_result_failure(self) -> None:
        result = CitationCheckResult.failure("Test error")

        assert result.success is False
        assert result.validated is False
        assert result.error == "Test error"


class TestCheckCitationsMock:
    """Test citation checking with mock adapter."""

    def test_check_citations_basic(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = CitationCheckInput(
            generated_content="CRISPR works in neurons and enables gene therapy.",
            source_texts=[
                SourceText(
                    text="Scientists demonstrated CRISPR gene editing in neuronal cells.",
                    source_name="Nature",
                    source_type="journal",
                ),
            ],
            content_type="takeaway",
        )

        result = check_citations(input_data, adapter=mock_adapter)

        assert isinstance(result, CitationCheckResult)
        assert result.success is True

    def test_check_citations_no_content_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = CitationCheckInput(
            generated_content="",
            source_texts=[SourceText(text="Source", source_name="Test")],
        )

        result = check_citations(input_data, adapter=mock_adapter)

        assert result.success is False

    def test_check_citations_no_sources_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = CitationCheckInput(
            generated_content="Some content",
            source_texts=[],
        )

        result = check_citations(input_data, adapter=mock_adapter)

        assert result.success is False


class TestCheckTakeawayCitations:
    """Test takeaway citation checking convenience function."""

    def test_check_takeaway_citations(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        takeaway = "Scientists developed a new CRISPR technique for neurons."
        sources = [
            {
                "text": "Researchers demonstrated CRISPR editing in neuronal tissue.",
                "source_name": "Science",
                "source_type": "journal",
            },
        ]

        result = check_takeaway_citations(takeaway, sources, adapter=mock_adapter)

        assert result.success is True


# ─────────────────────────────────────────────────────────────────────────────
# Citation Check Tests - Integration (Claude CLI)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckCitationsClaude:
    """Integration tests for citation checking with Claude CLI."""

    def test_check_supported_claim(
        self,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        input_data = CitationCheckInput(
            generated_content="The FDA approved Casgevy for sickle cell disease treatment.",
            source_texts=[
                SourceText(
                    text="The FDA has approved Casgevy (exagamglogene autotemcel), "
                    "a CRISPR-based gene therapy for sickle cell disease.",
                    source_name="FDA Press Release",
                    source_type="government",
                ),
            ],
            content_type="takeaway",
        )

        result = check_citations(input_data, adapter=claude_adapter)

        assert result.success is True, f"Check failed: {result.error}"
        # Should validate since claim matches source
        assert result.validated is True or result.confidence > 0.7

    def test_check_overstated_claim(
        self,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        input_data = CitationCheckInput(
            generated_content="This breakthrough cure eliminates all genetic diseases forever.",
            source_texts=[
                SourceText(
                    text="The therapy shows promise for treating sickle cell disease "
                    "in clinical trials with some patients.",
                    source_name="Research Paper",
                    source_type="journal",
                ),
            ],
            content_type="takeaway",
        )

        result = check_citations(input_data, adapter=claude_adapter)

        assert result.success is True
        # Should flag the overstatement
        if result.validated:
            # If validated, confidence should be low
            assert result.confidence < 0.9
        else:
            # If not validated, should have flags
            assert len(result.flags) > 0 or result.confidence < 0.7


# ─────────────────────────────────────────────────────────────────────────────
# Result Dataclass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestIntuitionResultDataclass:
    """Test IntuitionResult dataclass."""

    def test_create_success_result(self) -> None:
        result = IntuitionResult(
            intuition="Test intuition text",
            analogies_used=["scissors", "key"],
            confidence=0.85,
            model="test-model",
            success=True,
        )

        assert result.intuition == "Test intuition text"
        assert len(result.analogies_used) == 2
        assert result.success is True

    def test_create_failure_result(self) -> None:
        result = IntuitionResult.failure("Test error")

        assert result.intuition == ""
        assert result.analogies_used == []
        assert result.success is False
        assert result.error == "Test error"


class TestDeepDiveResultDataclass:
    """Test DeepDiveResult dataclass."""

    def test_create_success_result(self) -> None:
        content = DeepDiveContent(
            what_happened="Test",
            why_it_matters="Test",
            background="Test",
            limitations=[],
            whats_next="Test",
            related_concepts=[],
            generated_at="2026-02-05",
            source_count=1,
        )
        result = DeepDiveResult(
            content=content,
            raw_json={},
            confidence=0.8,
            model="test",
            success=True,
        )

        assert result.content is not None
        assert result.success is True

    def test_create_failure_result(self) -> None:
        result = DeepDiveResult.failure("Test error")

        assert result.content is None
        assert result.success is False
        assert result.error == "Test error"
