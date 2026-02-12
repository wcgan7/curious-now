"""LLM-based impact rater (shadow-mode compatible)."""

from __future__ import annotations

from dataclasses import dataclass

from curious_now.ai.llm_adapter import LLMAdapter, get_llm_adapter


@dataclass(frozen=True)
class ImpactRaterInput:
    """Input context for LLM impact scoring."""

    cluster_title: str
    takeaway: str
    deep_dive_markdown: str | None
    content_types: list[str]
    distinct_source_count: int


@dataclass(frozen=True)
class ImpactRaterResult:
    """Structured LLM impact scoring output."""

    novelty_score: float
    translation_score: float
    evidence_score: float
    confidence: float
    reasoning: str
    model: str
    success: bool = True
    error: str | None = None

    @property
    def impact_score(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                0.45 * self.novelty_score
                + 0.40 * self.translation_score
                + 0.15 * self.evidence_score,
            ),
        )

    @staticmethod
    def failure(error: str) -> ImpactRaterResult:
        return ImpactRaterResult(
            novelty_score=0.0,
            translation_score=0.0,
            evidence_score=0.0,
            confidence=0.0,
            reasoning="",
            model="unknown",
            success=False,
            error=error,
        )


def blend_impact_scores(
    deterministic_score: float,
    llm_score: float,
    *,
    deterministic_weight: float = 0.4,
    llm_weight: float = 0.6,
) -> float:
    """Blend deterministic and LLM impact scores with normalized weights."""
    total = deterministic_weight + llm_weight
    if total <= 0:
        return max(0.0, min(1.0, deterministic_score))
    det_w = deterministic_weight / total
    llm_w = llm_weight / total
    blended = det_w * deterministic_score + llm_w * llm_score
    return max(0.0, min(1.0, blended))


_SYSTEM_PROMPT = """You are an expert research evaluator.
Score research impact conservatively and avoid hype.

Output must be a JSON object with:
- novelty_score (0..1)
- translation_score (0..1)
- evidence_score (0..1)
- confidence (0..1)
- reasoning (<= 2 sentences)

Rubric:
- novelty_score: non-redundancy and originality versus typical work.
- translation_score: plausible practical downstream impact in real settings.
- evidence_score: support quality from study type/source reliability/context.

Do not include markdown. Return only JSON."""


_USER_PROMPT_TEMPLATE = """Evaluate this research cluster.

Title: {cluster_title}
Takeaway: {takeaway}
Content Types: {content_types}
Distinct Sources: {distinct_source_count}

Deep Dive (optional):
{deep_dive}

Return only JSON with the required keys."""


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rate_impact_with_llm(
    input_data: ImpactRaterInput,
    *,
    adapter: LLMAdapter | None = None,
) -> ImpactRaterResult:
    """Rate impact components with LLM; safe for shadow-mode use."""
    if not input_data.cluster_title or not input_data.takeaway:
        return ImpactRaterResult.failure("Missing title or takeaway")
    if adapter is None:
        adapter = get_llm_adapter()
    if getattr(adapter, "name", "") == "mock":
        return ImpactRaterResult.failure("LLM adapter unavailable (mock fallback)")

    deep_dive = (input_data.deep_dive_markdown or "").strip()
    if len(deep_dive) > 2400:
        deep_dive = deep_dive[:2400] + "..."

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        takeaway=input_data.takeaway,
        content_types=", ".join(input_data.content_types[:8]),
        distinct_source_count=input_data.distinct_source_count,
        deep_dive=deep_dive or "(none)",
    )

    raw_json = adapter.complete_json(
        user_prompt,
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=500,
    )
    model_name = getattr(adapter, "model", adapter.name)
    if raw_json is None:
        return ImpactRaterResult.failure("Failed to parse LLM JSON response")

    novelty = _clamp(_to_float(raw_json.get("novelty_score"), 0.0))
    translation = _clamp(_to_float(raw_json.get("translation_score"), 0.0))
    evidence = _clamp(_to_float(raw_json.get("evidence_score"), 0.0))
    confidence = _clamp(_to_float(raw_json.get("confidence"), 0.0))
    reasoning = str(raw_json.get("reasoning") or "").strip()
    if not reasoning:
        reasoning = "No reasoning provided."

    return ImpactRaterResult(
        novelty_score=novelty,
        translation_score=translation,
        evidence_score=evidence,
        confidence=confidence,
        reasoning=reasoning,
        model=model_name,
        success=True,
    )
