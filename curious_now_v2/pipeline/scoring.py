"""The feed's sort key: what a story earned, and when it was published.

Two decisions shape this.

**Quality multiplies freshness rather than adding to it.** With
`score = Q · exp(-(now - t)/h)`, taking logarithms and multiplying by `h` gives
`(t + h·ln Q) - now`, and the clock term is identical for every story, so it
cancels out of every comparison. `t + h·ln Q` therefore never needs recomputing:
it is written once, when the story is published, and stays correct. The previous
additive score changed twelve of its top twelve positions within a month, and
past 532 days it underflowed `exp(-age/h)` to zero and tied every older story
together.

**Every factor is a time.** `h·ln(factor)` converts a multiplier into hours, so
a story ranks as if published earlier by an amount its shortcomings cost it.
That is the whole reason the score is readable: an operator asking why one story
sits above another gets an answer in hours rather than in arbitrary points.

What is deliberately absent is as important. Provenance -- peer-reviewed against
preprint -- is a fact worth showing a reader and not a claim about whether the
science is interesting, so it is a badge rather than a term here. Our own
retrieval success is not a property of the story. Press pickup is not what this
feed is for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log

FRESHNESS_HALF_LIFE_HOURS = 18.0

# How many rungs the story earned. Not asserted: three rungs means the Explain
# survived a judge that had to quote its mechanism sentence, and the Technical
# cited figures that exist in the document. Measured across 168 published
# stories, this splits them 12% / 57% / 31%.
QUALITY_BY_RUNGS: dict[int, float] = {3: 1.0, 2: 0.70, 1: 0.45}
RUNGS_FALLBACK = 0.45

# Whether the result would change what someone in the field does next. Weighted
# harder than rungs on purpose: rungs measure how well we could explain a paper,
# significance measures whether it mattered, and the second is the editorial
# question this feed exists to answer.
QUALITY_BY_SIGNIFICANCE: dict[str, float] = {
    "changes_practice": 1.0,
    "incremental": 0.55,
    "unclear": 0.35,
}
SIGNIFICANCE_FALLBACK = 0.35


@dataclass(frozen=True)
class ScoreComponent:
    """One multiplier, and what it costs in hours."""

    name: str
    value: str
    factor: float
    offset_hours: float

    def describe(self) -> str:
        return f"{self.name} {self.value}: x{self.factor:.2f} ({self.offset_hours:+.1f}h)"


@dataclass(frozen=True)
class StoryScore:
    quality: float
    offset_hours: float
    effective_at: datetime
    components: tuple[ScoreComponent, ...]

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(component.describe() for component in self.components)


def _component(name: str, value: str, factor: float, half_life: float) -> ScoreComponent:
    return ScoreComponent(name, value, factor, half_life * log(factor))


def score_story(
    *,
    published_at: datetime,
    rungs_earned: int,
    significance: str,
    half_life_hours: float = FRESHNESS_HALF_LIFE_HOURS,
) -> StoryScore:
    """The sort key for one story, and the reasons behind it.

    `published_at` is the item's publication date -- when the science appeared
    -- not when we got round to publishing it.
    """

    rungs = QUALITY_BY_RUNGS.get(rungs_earned, RUNGS_FALLBACK)
    weight = QUALITY_BY_SIGNIFICANCE.get(significance, SIGNIFICANCE_FALLBACK)

    components = (
        _component("rungs", str(rungs_earned), rungs, half_life_hours),
        _component("significance", significance, weight, half_life_hours),
    )
    offset = sum(component.offset_hours for component in components)

    return StoryScore(
        quality=rungs * weight,
        offset_hours=offset,
        effective_at=published_at + timedelta(hours=offset),
        components=components,
    )
