from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.retrieval.quality import TextVerdict, assess_text


@dataclass(frozen=True)
class ItemText:
    """One item's retrieved text, as the gate needs to see it."""

    source_name: str
    text: str
    has_structure: bool = False
    is_primary_material: bool = False
    words: int = 0


class StoryGate(BaseModel):
    """Whether a story's evidence can support anything worth opening."""

    model_config = ConfigDict(frozen=True)

    publishable: bool
    supported_depths: tuple[ExplanationDepth, ...]
    grounding_source: str | None
    reasons: tuple[str, ...] = ()


def gate_story(items: tuple[ItemText, ...]) -> StoryGate:
    """Decide what a story's retrieved text can ground.

    Depth is judged from the richest single item rather than from everything
    concatenated. Two thin articles do not add up to a mechanism, and the word
    thresholds were calibrated against whole documents; combining them would
    claim a depth no single source actually supports.

    This is the text half of the publication rule. The other half — a validated
    presentation set — is applied once generation exists; until then a story
    that clears this gate is publishable in principle, not yet in fact.
    """

    usable = [item for item in items if item.text.strip()]
    if not usable:
        return StoryGate(
            publishable=False,
            supported_depths=(),
            grounding_source=None,
            reasons=("no item yielded any text",),
        )

    assessments = []
    for item in usable:
        assessment = assess_text(item.text, has_structure=item.has_structure)
        assessments.append((item, assessment))

    walled = [
        item.source_name
        for item, assessment in assessments
        if assessment.verdict is TextVerdict.SOFT_PAYWALL
    ]
    candidates = [
        (item, assessment)
        for item, assessment in assessments
        if assessment.verdict is TextVerdict.USABLE
    ]
    if not candidates:
        reasons = ["no item served text an explanation could rest on"]
        if walled:
            reasons.append(f"behind a paywall: {', '.join(sorted(set(walled)))}")
        return StoryGate(
            publishable=False,
            supported_depths=(),
            grounding_source=None,
            reasons=tuple(reasons),
        )

    item, assessment = max(
        candidates, key=lambda entry: len(entry[1].supported_depths)
    )
    depths = list(assessment.supported_depths)

    # Technical inspects the work itself, so it needs primary material, not
    # coverage of it — however well that coverage is written.
    if ExplanationDepth.TECHNICAL in depths and not item.is_primary_material:
        depths.remove(ExplanationDepth.TECHNICAL)

    reasons = [
        f"grounded in {item.source_name} ({assessment.words} words)",
        *assessment.reasons,
    ]
    if len(candidates) > 1:
        reasons.append(f"{len(candidates)} items carry usable text")
    if walled:
        reasons.append(f"behind a paywall: {', '.join(sorted(set(walled)))}")

    return StoryGate(
        publishable=bool(depths),
        supported_depths=tuple(depths),
        grounding_source=item.source_name,
        reasons=tuple(reasons),
    )
