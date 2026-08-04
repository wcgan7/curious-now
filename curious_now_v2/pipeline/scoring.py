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

**Ties are broken by rotating sources, not by row id.** Both terms above are
coarse -- see ROTATION_SECONDS -- so a great many stories share a key exactly.
Left alone the order falls to the UUID, which put 110 stories from one
publisher at the top of the feed in an order that meant nothing. A second per
place in a source's queue turns that block into a round robin. It is not a
judgement about the stories and does not appear in their reasons.

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

# One week. Inherited as 18 hours from the additive score and wrong there:
# freshness was 35% of a weighted sum then, and is the entire ordering backbone
# now, so the parameter had to be re-derived rather than carried across. At 18
# hours the whole quality range was worth 33 hours against a corpus spanning
# months, and the age bands did not overlap at all -- a three-rung
# practice-changing paper sat below every two-day-old story regardless of what
# it said. A week makes quality worth about thirteen days of age, which is the
# right trade for a feed that is calm rather than breaking.
FRESHNESS_HALF_LIFE_HOURS = 168.0

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

# One second per place in the queue, subtracted to break a tie.
#
# Both terms of the key are coarse. Publication dates carry no sub-day
# resolution -- 84% of ingested items land exactly on the hour, because arXiv
# stamps everything 04:00 and eLife, medRxiv and Nature 00:00 -- and quality
# takes nine values, all whole hours. Their sum lands 974 published stories on
# 460 distinct keys, 110 of them sharing the newest. Within a tie the order
# falls to the row id, which is a random UUID: stable, and meaningless.
#
# So a story is nudged earlier by its position among the stories from the same
# source landing on the same key. Reading the column then walks a tie as a
# round robin -- every source's first story, then every source's second --
# instead of as one publisher's whole day followed by another's.
#
# A second is small enough to be certain it decides nothing else. The closest
# two quality bands sit 1.7 hours apart, and the largest tie ever observed was
# 101 stories, so the largest shift this can produce is 101 seconds: a 60x
# margin. A minute was tried first and cleared the same gap by 1.3x, which is
# not a margin.
ROTATION_SECONDS = 1.0


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
    queue_position: int = 0,
    half_life_hours: float = FRESHNESS_HALF_LIFE_HOURS,
) -> StoryScore:
    """The sort key for one story, and the reasons behind it.

    `published_at` is the item's publication date -- when the science appeared
    -- not when we got round to publishing it.

    `queue_position` is how many stories from the same source already hold this
    story's key. It is knowable when the story is published and never changes
    afterwards, because a later story takes a higher position and an earlier one
    is never revisited -- so the key stays written-once, which is the property
    the whole design rests on.
    """

    rungs = QUALITY_BY_RUNGS.get(rungs_earned, RUNGS_FALLBACK)
    weight = QUALITY_BY_SIGNIFICANCE.get(significance, SIGNIFICANCE_FALLBACK)

    components = (
        _component("rungs", str(rungs_earned), rungs, half_life_hours),
        _component("significance", significance, weight, half_life_hours),
    )
    quality_offset = sum(component.offset_hours for component in components)

    # Kept out of `components`, and out of `quality`, on purpose. The reasons
    # exist so an operator can ask why one story sits above another and get an
    # answer in hours; a fraction of a second is not an answer, and listing it
    # would imply the story was judged worse, which it was not.
    rotation_hours = -(max(queue_position, 0) * ROTATION_SECONDS) / 3600

    return StoryScore(
        quality=rungs * weight,
        offset_hours=quality_offset,
        effective_at=published_at + timedelta(hours=quality_offset + rotation_hours),
        components=components,
    )
