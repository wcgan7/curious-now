# Curious Now v2 — Ranking on what we learned by reading

## The problem, stated properly

113 of 168 published stories sit at `feed_score = 0`, every one published since
`run_ranking` last ran. That is the visible defect. Two deeper ones sit under
it.

**The score measures our plumbing, not the science.** Its four components are
evidence quality (what *kind* of document this is), primary availability
(whether **we** obtained the paper), text sufficiency (how much text **our
retrieval** captured), and corroboration (how many outlets picked it up). Three
of the four describe our own machinery. None of them read the paper.

Meanwhile the pipeline read every word: it extracted claims against evidence,
classified the available evidence and generated the depths that source could
support. Ranking consults whether eligible generation completed, rather than
rewarding a source merely for being long enough to support more layers.

**And freshness cannot be stored.** At an 18-hour half-life a written score is
wrong within hours, so scheduling `run_ranking` after generation shortens the
window in which the feed is wrong without closing it.

## What ranking may read, measured

Only signals the pipeline already produced and already validated. Each was
checked against the 168 published stories before being kept.

**Eligible-depth completion — kept.** A complete Idea-only news story and a
complete three-layer paper both receive the top band. Lower bands mean a model
call failed for a depth that the selected source was capable of supporting.
This measures pipeline completeness without turning source complexity into a
quality judgement.

**Claim kinds — rejected.** 165 of 168 packets carry a `result` claim. At 98%
prevalence it separates nothing. `limitation` (73%) and `uncertainty` (79%)
looked more promising and are still too flat to carry weight, and both plausibly
measure the extractor rather than the paper.

**Claim count — rejected.** It runs from 3 to 104 across published packets and
tracks how long the document was. A 104-claim packet is a long paper, not a
good one.

So the free signals amount to **one three-level variable**. That is coarser
than anyone would want, and it is still far better aligned than ranking on
whether our fetcher succeeded.

## Quality

```
Q = QUALITY_BY_RUNGS[completion_band] x QUALITY_BY_SIGNIFICANCE[verdict]

completion    3 -> 1.00   2 -> 0.70   1 -> 0.45
significance  changes_practice -> 1.00   incremental -> 0.55   unclear -> 0.35
```

Both are tables rather than formulas, because neither approximates an
underlying continuous quantity and pretending otherwise would invite false
precision.

Significance is weighted harder than completion deliberately: completion
measures whether our pipeline finished its eligible work, while significance
measures whether the result mattered, and the second is the editorial question
this feed exists to answer.

## Provenance is not quality, and stops being folded in

`content_type` was doing duty as "evidence quality" and it is nothing of the
kind. Whether a paper is peer-reviewed or a preprint is a **fact about
provenance**, useful and worth knowing, and not a claim about whether the
science is interesting. Folding it into a single number both overstates it —
a dull peer-reviewed paper outranks a striking preprint on type alone — and
hides it, because the reader never sees the fact that actually mattered.

It leaves the score and becomes a badge on the story. `access_class` and
corroboration leave too: the first is a property of our retrieval, and the
second is a proxy for press pickup, which is not what this feed is for.

## The sort key

Combine quality and freshness by multiplication rather than addition, and the
ordering becomes computable once and correct forever. With
`score = Q · exp(-(now - t) / h)`, take logarithms and multiply by `h`:

```
h · ln(score)  =  (t + h · ln Q)  −  now
                                     ^^^^^ identical for every story
```

The clock term is common to all stories and cancels out of every comparison, so
**`t + h · ln Q` never needs recomputing**. Stored as a time:

```
effective_at = COALESCE(max(item.published_at), stories.created_at)
                 + (h · ln Q) hours
ORDER BY effective_at DESC, id DESC
```

It reads plainly: a story ranks as if published earlier by an amount its quality
earns. At `h = 18h` and the table above, a two-rung story behaves as though it
were 7.7 hours older than a three-rung one, and a one-rung story 18.9 hours
older.

The equivalence was checked over 400 synthetic stories at horizons from one hour
to five years and holds exactly, with one instructive exception: beyond about
**532 days** the live score underflows, because `exp(-age/h)` reaches `0.0` in
double precision, tying every older story together. Log space has no such limit,
so the stored key is not merely equivalent to the live computation but better
behaved than it. For contrast, the current additive score changes **12 of its
top 12 positions in a month**.

The time base is the **item's** publication date — how recent the science is —
not `stories.published_at`. The two coincide for most of this corpus, because
ingestion already sets the story's date from its item; they diverge for four of
168 by up to two days. Small, but they are different quantities, and only one of
them is about the science.

## Where it is computed

**No model call.** Rungs earned is a count of valid explanations, known in the
same transaction that publishes the story. The key goes in `db/generation.py`,
in the statement that sets `status = 'published'` — the only place a story
becomes published. The gate is deliberately not that place: it decides
eligibility and sets `draft`.

`run_ranking` stops being a periodic job and survives as an explicit recompute,
for the one case that needs it: a change to the table or the half-life, which
invalidates every key at once.

## Composition is not quality

The final shelf is not a single top-N query. The reader selects two independent
lanes using the grounding item: journalism and news-like document types are
accessible; primary research and other document types are technical. It keeps
the stored `effective_at` order inside each lane, deals principal sources
round-robin inside the selected batch, and interleaves two technical stories
for every accessible one. A twenty-story page therefore normally contains
fourteen technical and six accessible stories, with either lane allowed to
fill spare positions if the other runs out.

Both lanes carry independent keyset cursors. This is essential: advancing one
global cursor past the fourteen selected technical rows would silently discard
accessible rows that ranked between them. Composition belongs at read time
because it describes the shelf, while `effective_at` describes the individual
story; neither source repetition nor readable format is a defect in a story's
quality score.

## Significance

Three levels is coarse. The obvious remedy is to ask the model, and the obvious
form of that question is the wrong one.

**Not a rating.** Independent scalar scores do not calibrate — an 8 from one
call means nothing against an 8 from another, and the model sees no corpus to
compare against. This project already learned the general form of that lesson:
the writer decided for itself whether it had explained, and "a writer asked to
write will generally find that it does". Two metrics were tried against real
output and both failed; a judge with a required verbatim quote agreed with an
independently framed second judge on twelve of thirteen.

So if significance is wanted, it takes the judge's shape — a specific question,
a categorical verdict, and a quote that can be checked:

> Does this report a result that would change what someone working in this
> field does next? Quote the sentence that establishes it.
> → `changes_practice | incremental | unclear`

Categorical and grounded composes into `Q`. A scalar does not.

Measured over 24 random published stories: **3 changes_practice, 18
incremental, 3 unclear**, and all 24 quoted evidence that traced back to the
source. That is the distribution the question should produce -- most research
extends a line rather than redirecting it, and saying so is not an insult. The
three `unclear` verdicts were a BBC piece and two lab blogs, where the question
genuinely cannot be answered from a product announcement; declining is the right
answer there rather than a failure.

It costs $0.012 a story, which is less than the citation typing and about $2
for everything published so far.

## Variety

Interleaving only rearranges the rows already inside one page. It cannot repair
a page whose ranked candidate set contains nineteen arXiv ML stories and one
other source, which is the measured shape of the 998-story corpus.

The assembly adjustment is therefore **source/category/day density**. Within a
cohort, stories take append-only positions in publication order and receive:

```
D(position) = 1 / (1 + 0.1 * position)
effective_at = published_at + h*ln(Q) + h*ln(D)
```

Position zero — the source's first story in that reader category that day — is
untouched. Position one moves back about 16 hours, position two about 31 hours,
and the curve continues smoothly. There is no quota: freshness and quality can
still overcome repetition. `D` stays outside `quality` because repetition is a
property of assembly, not a judgement about the work.

The category is part of the cohort because one source covering two genuinely
different fields should not make either story redundant. A 2026-08 simulation
compared whole-day, progressive-day, weekly and category-aware variants. The
chosen append-stable rule changed the first page from 2 to 12 sources, reduced
the largest source from 19/20 to 6/20, and represented all eight categories.
Every selected story remained in the top quality and significance band; median
age moved from 0.5 to 0.7 days.

The position and its identity are stored in `ranking_reasons`. Regeneration in
the same cohort reuses the position, concurrent publishers reserve positions
under a cohort-scoped advisory lock, and a recompute preserves stored positions
while appending anything new. Keyset pagination therefore remains stable.

## What changes

1. **Migration**: add `quality_score DOUBLE PRECISION` and
   `effective_at TIMESTAMPTZ`; index `(effective_at DESC, id DESC)
   WHERE status = 'published'`. Retire `feed_score` after the reader moves.
2. **`pipeline/scoring.py`**: `Q` from eligible-depth completion; drop evidence,
   primary, corroboration and text; apply density outside `Q`.
3. **`db/generation.py`**: reserve the append-only density position and write
   the key alongside `status = 'published'`.
4. **`db/ranking.py`**: preserve stored density positions during an explicit
   recompute and append any unpositioned stories.
5. **Reader**: order and paginate on `(effective_at, id)`; show provenance as a
   badge rather than as an input to the score.
6. **Backfill**: one recompute over the 168 already published.

## What this costs

**Ranking gets coarser before it gets better.** Three levels times freshness is
less expressive than five weighted components — but four of those five measured
the wrong thing, so the resolution being lost was mostly noise. The significance
judge is the route back to resolution, when it is needed.

**Old stories never resurface.** Under addition, freshness decays toward zero
for everything and ordering drifts back toward quality, so a good old story
climbs. Under a product the ordering fixed at publication is permanent. For a
calm feed that is the better behaviour, but it is a change and not a refactor.

**A table change means a full recompute**, explicitly, rather than implicitly on
the next pass. More honest, and easier to forget.
