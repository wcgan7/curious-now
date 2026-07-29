from __future__ import annotations

from datetime import datetime, timedelta
from math import exp
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from curious_now_v2.core.enums import AccessClass, ContentType, SourceRole
from curious_now_v2.core.models import StoryDraft

# Weights sum to 1.0 so a base score is directly readable as a 0-1 quality
# estimate before the variety damper is applied.
WEIGHT_FRESHNESS = 0.35
WEIGHT_EVIDENCE = 0.25
WEIGHT_PRIMARY = 0.15
WEIGHT_CORROBORATION = 0.15
WEIGHT_TEXT = 0.10

FRESHNESS_HALF_LIFE_HOURS = 18.0

EVIDENCE_QUALITY = {
    ContentType.PEER_REVIEWED: 1.0,
    ContentType.PREPRINT: 0.6,
    ContentType.REPORT: 0.6,
    ContentType.DATASET: 0.5,
    ContentType.LAB_ANNOUNCEMENT: 0.45,
    ContentType.NEWS: 0.4,
    ContentType.BLOG: 0.3,
    ContentType.PRESS_RELEASE: 0.25,
    ContentType.OTHER: 0.2,
}

TEXT_SUFFICIENCY = {
    AccessClass.OPEN_FULL_TEXT: 1.0,
    AccessClass.ABSTRACT: 0.7,
    AccessClass.SNIPPET: 0.4,
    AccessClass.METADATA_ONLY: 0.15,
}

INDEPENDENT_ROLES = frozenset(
    {SourceRole.JOURNALISM, SourceRole.INSTITUTIONAL, SourceRole.GOVERNMENT}
)

# Each additional story from one source in the same ranking pass is damped by
# this factor, so a bulk feed drop cannot occupy the whole shelf.
VARIETY_DECAY = 0.45
VARIETY_FLOOR = 0.08


class RankedStory(BaseModel):
    """A scored story with the reasons an operator can inspect."""

    model_config = ConfigDict(frozen=True)

    story_id: UUID
    score: float = Field(ge=0)
    base_score: float = Field(ge=0)
    variety_factor: float = Field(ge=0, le=1)
    principal_source: str | None
    reasons: tuple[str, ...]


def _freshness(story: StoryDraft, *, now: datetime) -> tuple[float, str]:
    published = [
        item.published_at for item in story.items if item.published_at is not None
    ]
    if not published:
        return 0.3, "no publication date; assumed mid-freshness"
    age = now - max(published)
    hours = max(age / timedelta(hours=1), 0.0)
    score = exp(-hours / FRESHNESS_HALF_LIFE_HOURS)
    if hours < 1:
        return score, "published within the hour"
    if hours < 48:
        return score, f"published {round(hours)}h ago"
    return score, f"published {round(hours / 24)}d ago"


def _evidence_quality(story: StoryDraft) -> tuple[float, str]:
    best_type = max(
        (item.content_type for item in story.items),
        key=lambda value: EVIDENCE_QUALITY.get(value, 0.2),
    )
    score = EVIDENCE_QUALITY.get(best_type, 0.2)
    return score, f"strongest evidence type is {best_type.value}"


def _primary_availability(story: StoryDraft) -> tuple[float, str]:
    if not story.has_primary_material:
        return 0.0, "no primary material attached"
    accessible = any(
        item.is_primary_material
        and item.access_class
        in {AccessClass.ABSTRACT, AccessClass.OPEN_FULL_TEXT}
        for item in story.items
    )
    if accessible:
        return 1.0, "primary material with accessible text"
    return 0.55, "primary material, metadata only"


def _corroboration(story: StoryDraft) -> tuple[float, str]:
    independent = {
        item.source_name
        for item in story.items
        if item.source_role in INDEPENDENT_ROLES
    }
    interested_only = all(
        item.source_role
        in {SourceRole.LAB_ANNOUNCEMENT, SourceRole.PRESS_RELEASE}
        for item in story.items
    )
    if len(independent) >= 2:
        return 1.0, f"{len(independent)} independent sources"
    if len(independent) == 1:
        return 0.6, "one independent source"
    if interested_only:
        return 0.0, "only interested-party sources"
    return 0.25, "no independent coverage yet"


def _text_sufficiency(story: StoryDraft) -> tuple[float, str]:
    access = story.best_access_class
    score = TEXT_SUFFICIENCY.get(access, 0.15)
    return score, f"best available text is {access.value}"


def score_story(story: StoryDraft, *, now: datetime) -> RankedStory:
    """Score one story from evidence signals only; never from engagement."""

    freshness, freshness_reason = _freshness(story, now=now)
    evidence, evidence_reason = _evidence_quality(story)
    primary, primary_reason = _primary_availability(story)
    corroboration, corroboration_reason = _corroboration(story)
    text, text_reason = _text_sufficiency(story)

    base = (
        WEIGHT_FRESHNESS * freshness
        + WEIGHT_EVIDENCE * evidence
        + WEIGHT_PRIMARY * primary
        + WEIGHT_CORROBORATION * corroboration
        + WEIGHT_TEXT * text
    )
    principal = story.items[0].source_name if story.items else None
    return RankedStory(
        story_id=story.story_id,
        score=base,
        base_score=base,
        variety_factor=1.0,
        principal_source=principal,
        reasons=(
            freshness_reason,
            evidence_reason,
            primary_reason,
            corroboration_reason,
            text_reason,
        ),
    )


def rank_stories(
    stories: tuple[StoryDraft, ...],
    *,
    now: datetime,
) -> tuple[RankedStory, ...]:
    """Score stories, then damp repeated sources so one bulk feed drop cannot
    occupy the whole shelf.

    Ranking is deterministic and uses no per-user engagement. Ties break on
    story ID so repeated runs produce a stable order.
    """

    scored = sorted(
        (score_story(story, now=now) for story in stories),
        key=lambda ranked: (-ranked.base_score, str(ranked.story_id)),
    )

    seen: dict[str, int] = {}
    damped: list[RankedStory] = []
    for ranked in scored:
        source = ranked.principal_source or "unknown source"
        repetition = seen.get(source, 0)
        seen[source] = repetition + 1
        factor = max(VARIETY_DECAY**repetition, VARIETY_FLOOR)
        reasons = ranked.reasons
        if repetition:
            reasons = (
                *reasons,
                f"variety damper: #{repetition + 1} from {source}",
            )
        damped.append(
            ranked.model_copy(
                update={
                    "score": ranked.base_score * factor,
                    "variety_factor": factor,
                    "reasons": reasons,
                }
            )
        )

    return tuple(
        sorted(damped, key=lambda ranked: (-ranked.score, str(ranked.story_id)))
    )
