from __future__ import annotations

from curious_now.impact_scoring import (
    HighImpactInput,
    compute_components,
    compute_high_impact_score,
    high_impact_passes_gates,
)


def test_compute_components_are_bounded() -> None:
    input_data = HighImpactInput(
        takeaway="A new clinical approach may reduce cost and improve outcomes for patients.",
        canonical_title="Novel model for clinical deployment",
        content_types=["peer_reviewed", "news"],
        anti_hype_flags=[],
        distinct_source_count=4,
        has_full_text_paper=True,
    )
    c = compute_components(input_data)
    assert 0.0 <= c.novelty_score <= 1.0
    assert 0.0 <= c.translation_score <= 1.0
    assert 0.0 <= c.evidence_score <= 1.0


def test_provisional_only_when_not_eligible() -> None:
    input_data = HighImpactInput(
        takeaway="New result with possible policy implications.",
        canonical_title="A new benchmark",
        content_types=["preprint"],
        anti_hype_flags=["single_source"],
        distinct_source_count=1,
        has_full_text_paper=False,
    )
    result = compute_high_impact_score(input_data)
    assert result.final_score is None
    assert result.eligible_for_final is False
    assert result.provisional_score > 0.0


def test_gate_requires_threshold_confidence_and_evidence() -> None:
    assert high_impact_passes_gates(
        final_score=0.99,
        confidence=0.80,
        evidence_score=0.50,
        threshold=0.95,
    )
    assert not high_impact_passes_gates(
        final_score=0.99,
        confidence=0.70,
        evidence_score=0.50,
        threshold=0.95,
    )
    assert not high_impact_passes_gates(
        final_score=0.99,
        confidence=0.80,
        evidence_score=0.20,
        threshold=0.95,
    )


def test_escape_hatch_allows_near_threshold_absolute_high_bar() -> None:
    assert high_impact_passes_gates(
        final_score=0.975,
        confidence=0.80,
        evidence_score=0.45,
        threshold=0.985,
    )


def test_qualified_set_override_allows_multiple_revolutionary_papers() -> None:
    assert high_impact_passes_gates(
        final_score=0.972,
        confidence=0.81,
        evidence_score=0.46,
        threshold=0.99,
        qualified_set_count=5,
    )


def test_translation_signal_scores_higher_for_real_world_takeaway() -> None:
    low = HighImpactInput(
        takeaway="This paper introduces a new architecture and reports benchmark gains.",
        canonical_title="A new model architecture",
        content_types=["preprint"],
        anti_hype_flags=[],
        distinct_source_count=1,
        has_full_text_paper=True,
    )
    high = HighImpactInput(
        takeaway=(
            "A clinical trial showed this method reduced patient complications by 20% "
            "and is now deployed in production workflows."
        ),
        canonical_title="Clinical deployment of a medical model",
        content_types=["peer_reviewed"],
        anti_hype_flags=[],
        distinct_source_count=1,
        has_full_text_paper=True,
    )
    low_c = compute_components(low)
    high_c = compute_components(high)
    assert high_c.translation_score > low_c.translation_score


def test_single_source_flag_does_not_change_component_scores() -> None:
    base = HighImpactInput(
        takeaway="A practical method for policy teams to reduce cost in real-world operations.",
        canonical_title="Operational policy optimizer",
        content_types=["preprint"],
        anti_hype_flags=[],
        distinct_source_count=1,
        has_full_text_paper=True,
    )
    flagged = HighImpactInput(
        takeaway=base.takeaway,
        canonical_title=base.canonical_title,
        content_types=base.content_types,
        anti_hype_flags=["single_source"],
        distinct_source_count=base.distinct_source_count,
        has_full_text_paper=base.has_full_text_paper,
    )
    base_c = compute_components(base)
    flagged_c = compute_components(flagged)
    assert flagged_c.evidence_score == base_c.evidence_score
    assert flagged_c.novelty_score == base_c.novelty_score
    assert flagged_c.translation_score == base_c.translation_score
