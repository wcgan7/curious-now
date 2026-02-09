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
    IntuitionInput,
    IntuitionResult,
    generate_eli5,
    generate_eli20,
    generate_intuition,
    generate_intuition_from_abstracts,
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
            # Matches ELI20 prompt section title
            "Canonical Deep Dive": "The method refines CRISPR so edits in neurons are more targeted and "
            "predictable, emphasizing control over where changes happen while preserving "
            "the intended therapeutic effect. It frames the core mechanism as tightening "
            "specificity in the editing step and pairing that with delivery choices that "
            "fit brain-cell constraints, so the approach stays practical for disease-focused "
            "applications without introducing new claims beyond the deep dive source.",
            # Matches ELI5 prompt section title
            "Conceptual Intuition (ELI20)": "This is about making a gene-editing approach safer and more reliable "
            "for brain cells. The problem is that tiny mistakes matter more in neurons, so "
            "the goal is to reduce off-target changes. At a high level, it improves how the "
            "editing tool picks where to act, then pairs that with a delivery setup suited "
            "to those cells, so treatment ideas can be explored with less unwanted editing.",
            # Matches "Technical Deep Dive" in deep_dive prompts
            "Technical Deep Dive": """## Overview

Scientists developed a modified CRISPR system that enables gene therapy in brain cells.

## Methodology / Approach

The team modified the Cas9 enzyme to reduce off-target effects in post-mitotic cells.

## Results

Clinical trials showed significant improvement in neurological function.

## Limitations & Uncertainties

- Only tested in mice so far
- High cost of treatment
- Limited availability of specialized facilities""",
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
        deep_dive_markdown=(
            "## Overview\\nA CRISPR variant was adapted for neurons.\\n\\n"
            "## Methodology / Approach\\nThe work improves targeting specificity and uses "
            "delivery suited to neuronal biology.\\n\\n"
            "## Results\\nThe deep dive reports improved precision relative to baseline."
        ),
    )


@pytest.fixture
def sample_deep_dive_input() -> DeepDiveInput:
    """Sample input for deep-dive generation."""
    return DeepDiveInput(
        cluster_title="FDA approves first CRISPR-based therapy",
        source_summaries=[
            SourceSummary(
                title="FDA Approves First CRISPR Therapy for Sickle Cell Disease",
                snippet=(
                    "The FDA has approved Casgevy, developed by Vertex and CRISPR "
                    "Therapeutics, for treating sickle cell disease in patients 12+."
                ),
                source_name="FDA Press Release",
                source_type="government",
                full_text=(
                    "The FDA has approved Casgevy (exagamglogene autotemcel), developed "
                    "by Vertex Pharmaceuticals and CRISPR Therapeutics, for treating "
                    "sickle cell disease in patients 12 years and older. This is the "
                    "first FDA-approved therapy using CRISPR gene-editing technology. "
                    "The treatment involves extracting a patient's bone marrow stem cells, "
                    "editing them using CRISPR to produce functional hemoglobin, and "
                    "reinfusing the modified cells. Clinical trials showed 93% of patients "
                    "were free of vaso-occlusive crises for at least 12 months after treatment."
                ),
            ),
            SourceSummary(
                title="CRISPR gene therapy receives landmark FDA approval",
                snippet="The approval marks the first time a CRISPR-based therapy has been "
                "authorized for use in the United States.",
                source_name="Nature",
                source_type="journal",
                full_text=(
                    "The approval marks the first time a CRISPR-based therapy has been "
                    "authorized for use in the United States, representing a landmark moment "
                    "for gene editing technology. The therapy targets BCL11A, a gene that "
                    "normally suppresses fetal hemoglobin production. By disrupting this gene, "
                    "the treatment reactivates fetal hemoglobin, which can compensate for "
                    "the defective adult hemoglobin in sickle cell disease."
                ),
            ),
            SourceSummary(
                title="What the first CRISPR therapy approval means for patients",
                snippet="The treatment costs approximately $2.2 million and requires "
                "hospitalization for bone marrow extraction.",
                source_name="STAT News",
                source_type="journalism",
                full_text=(
                    "The treatment costs approximately $2.2 million and requires "
                    "hospitalization for bone marrow extraction and chemotherapy conditioning. "
                    "Patients must undergo myeloablative conditioning to make room for the "
                    "edited cells. The process takes several months from cell collection to "
                    "reinfusion. While the therapy shows promise, questions remain about "
                    "long-term durability and accessibility for the approximately 100,000 "
                    "Americans living with sickle cell disease."
                ),
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Intuition Tests - Unit
# ─────────────────────────────────────────────────────────────────────────────


class TestLayeredIntuition:
    """Test staged intuition generation helpers."""

    def test_generate_eli20_from_deep_dive(
        self,
        sample_intuition_input: IntuitionInput,
        mock_adapter: MockAdapter,
    ) -> None:
        eli20_text, _, _, word_count, _ = generate_eli20(sample_intuition_input, adapter=mock_adapter)
        assert len(eli20_text) > 0
        assert word_count > 20

    def test_generate_eli5_from_eli20(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        eli5_text, _, _, word_count, _ = generate_eli5(
            cluster_title="Test",
            eli20_text="A precise conceptual explanation of how a CRISPR variant improves targeting.",
            adapter=mock_adapter,
        )
        assert len(eli5_text) > 0
        assert word_count > 20


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

    def test_generate_intuition_returns_both_layers(
        self,
        sample_intuition_input: IntuitionInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_intuition(sample_intuition_input, adapter=mock_adapter)

        assert result.success is True
        assert len(result.eli20) > 0
        assert len(result.eli5) > 0

    def test_generate_intuition_no_title_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = IntuitionInput(cluster_title="", deep_dive_markdown="text")
        result = generate_intuition(input_data, adapter=mock_adapter)

        assert result.success is False
        assert result.error is not None and "title" in result.error.lower()

    def test_generate_intuition_missing_deep_dive_fails(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        input_data = IntuitionInput(cluster_title="CRISPR")
        result = generate_intuition(input_data, adapter=mock_adapter)

        assert result.success is False
        assert result.error is not None and "deep dive" in result.error.lower()

    def test_generate_intuition_from_abstracts_returns_eli5_only(
        self,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_intuition_from_abstracts(
            cluster_title="CRISPR abstract-only cluster",
            abstracts_text="This abstract describes a CRISPR variant with improved targeting.",
            adapter=mock_adapter,
        )
        assert result.success is True
        assert len(result.eli5) > 0
        assert result.eli20 == ""


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
        assert len(result.eli5) > 50
        assert len(result.eli20) > 50
        assert result.confidence > 0.5

    def test_eli5_uses_simple_language(
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
        intuition_lower = result.eli5.lower()
        for word in jargon_words:
            assert word not in intuition_lower, (
                f"Intuition contains jargon '{word}': {result.eli5}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Deep Dive Tests - Unit
# ─────────────────────────────────────────────────────────────────────────────


class TestDeepDiveContent:
    """Test DeepDiveContent dataclass."""

    def test_deep_dive_to_json(self) -> None:
        content = DeepDiveContent(
            markdown="## Overview\n\nTest content here.",
            generated_at="2026-02-05T10:00:00Z",
            source_count=3,
        )

        json_data = deep_dive_to_json(content)

        assert "## Overview" in json_data["markdown"]
        assert json_data["source_count"] == 3
        assert json_data["generated_at"] == "2026-02-05T10:00:00Z"

    def test_deep_dive_from_json(self) -> None:
        json_data = {
            "markdown": "## Overview\n\nTest happened.",
            "generated_at": "2026-02-05T10:00:00Z",
            "source_count": 2,
        }

        content = deep_dive_from_json(json_data)

        assert content is not None
        assert "## Overview" in content.markdown
        assert content.source_count == 2

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

    def test_generate_deep_dive_has_markdown_content(
        self,
        sample_deep_dive_input: DeepDiveInput,
        mock_adapter: MockAdapter,
    ) -> None:
        result = generate_deep_dive(sample_deep_dive_input, adapter=mock_adapter)

        assert result.success is True
        assert result.content is not None
        assert len(result.content.markdown) > 0
        # Should have headers (##)
        assert "##" in result.content.markdown

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

        # Check markdown has substantial content
        assert len(result.content.markdown) > 200
        # Should have headers
        assert "##" in result.content.markdown

    def test_deep_dive_includes_methodology_or_results(
        self,
        sample_deep_dive_input: DeepDiveInput,
        claude_adapter: ClaudeCLIAdapter,
    ) -> None:
        if not claude_adapter.is_available():
            pytest.skip("Claude CLI not available")

        result = generate_deep_dive(sample_deep_dive_input, adapter=claude_adapter)

        assert result.success is True
        assert result.content is not None
        markdown_lower = result.content.markdown.lower()
        # Should mention methodology, results, or approach
        assert any(word in markdown_lower for word in ["method", "result", "approach"])

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
            intuition="Test ELI5",
            eli20="Test ELI20",
            eli5="Test ELI5",
            confidence=0.85,
            model="test-model",
            success=True,
        )

        assert result.intuition == "Test ELI5"
        assert result.eli20 == "Test ELI20"
        assert result.eli5 == "Test ELI5"
        assert result.success is True

    def test_create_failure_result(self) -> None:
        result = IntuitionResult.failure("Test error")

        assert result.intuition == ""
        assert result.eli20 == ""
        assert result.eli5 == ""
        assert result.success is False
        assert result.error == "Test error"


class TestDeepDiveResultDataclass:
    """Test DeepDiveResult dataclass."""

    def test_create_success_result(self) -> None:
        content = DeepDiveContent(
            markdown="## Overview\n\nTest content.",
            generated_at="2026-02-05",
            source_count=1,
        )
        result = DeepDiveResult(
            content=content,
            raw_json={"markdown": content.markdown},
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
