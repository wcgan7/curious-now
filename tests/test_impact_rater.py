from __future__ import annotations

from curious_now.ai.impact_rater import (
    ImpactRaterInput,
    blend_impact_scores,
    rate_impact_with_llm,
)


class _FakeAdapter:
    def __init__(self, payload: dict | None, model: str = "fake-model") -> None:
        self._payload = payload
        self.model = model
        self.name = "fake"

    def complete_json(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return self._payload


def test_rate_impact_with_llm_success_and_clamp() -> None:
    adapter = _FakeAdapter(
        {
            "novelty_score": 1.2,
            "translation_score": 0.7,
            "evidence_score": -0.1,
            "confidence": 2.0,
            "reasoning": "Strong practical pathway.",
        }
    )
    result = rate_impact_with_llm(
        ImpactRaterInput(
            cluster_title="Test title",
            takeaway="Test takeaway",
            deep_dive_markdown="Test deep dive",
            content_types=["preprint"],
            distinct_source_count=1,
        ),
        adapter=adapter,  # type: ignore[arg-type]
    )
    assert result.success is True
    assert result.novelty_score == 1.0
    assert result.translation_score == 0.7
    assert result.evidence_score == 0.0
    assert result.confidence == 1.0
    assert 0.0 <= result.impact_score <= 1.0


def test_rate_impact_with_llm_failure_when_no_json() -> None:
    adapter = _FakeAdapter(None)
    result = rate_impact_with_llm(
        ImpactRaterInput(
            cluster_title="Test title",
            takeaway="Test takeaway",
            deep_dive_markdown=None,
            content_types=["preprint"],
            distinct_source_count=1,
        ),
        adapter=adapter,  # type: ignore[arg-type]
    )
    assert result.success is False
    assert result.error is not None


def test_blend_impact_scores_uses_40_60_weights() -> None:
    blended = blend_impact_scores(0.50, 0.80, deterministic_weight=0.4, llm_weight=0.6)
    assert abs(blended - 0.68) < 1e-9
