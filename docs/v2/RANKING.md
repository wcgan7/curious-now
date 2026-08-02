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
ran a second judge over whether Explain states a mechanism, and wrote a
Technical walkthrough whose citations were validated against recoverable figure
labels. Ranking consults none of it. A story that earned all four rungs and one
that managed two are indistinguishable to the feed unless their content types
happen to differ.

**And freshness cannot be stored.** At an 18-hour half-life a written score is
wrong within hours, so scheduling `run_ranking` after generation shortens the
window in which the feed is wrong without closing it.

## What ranking may read, measured

Only signals the pipeline already produced and already validated. Each was
checked against the 168 published stories before being kept.

**Rungs earned — kept.** The one signal that discriminates.

```
1 depth:  20 stories (12%)
2 depths: 96 stories (57%)
3 depths: 52 stories (31%)

explain    138 valid,  30 failed
technical   62 valid,  10 failed
```

This is earned, not asserted. A story reaches three rungs only if its Explain
survived a judge that had to quote the mechanism sentence verbatim, and its
Technical cited figures that exist in the document. The thirty failures are
recorded with their reasons — "judged a capability list rather than a
mechanism" — which is a real editorial verdict about the source's substance.

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
Q = QUALITY_BY_RUNGS[rungs_earned] x QUALITY_BY_SIGNIFICANCE[verdict]

rungs         3 -> 1.00   2 -> 0.70   1 -> 0.45
significance  changes_practice -> 1.00   incremental -> 0.55   unclear -> 0.35
```

Both are tables rather than formulas, because neither approximates an
underlying continuous quantity and pretending otherwise would invite false
precision.

Significance is weighted harder than rungs deliberately: rungs measure how well
we could explain a paper, significance measures whether it mattered, and the
second is the editorial question this feed exists to answer. A one-rung paper
that changes practice therefore outranks a three-rung paper that does not.

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

The damper leaves the score. It multiplies by `0.45 ** repetition` counted
**within a ranking pass**, so two stories of identical merit take different
permanent scores depending on which batch ranked them. That is not a property
of a story.

Removing it leaves real clumping — the corpus has source-days of up to 10
published stories. **Phase one removes it and does nothing else**, so the shape
can be seen before it is designed against.

**Phase two diversifies at assembly**: paginate by `effective_at` so each story
falls on exactly one page, then interleave by source within the page. The page
boundary stays keyset-stable while reading order spreads sources out.

If that proves insufficient, the escalation is **source-day density** — shift
`effective_at` back by `h · ln(1 / (1 + λ(n − 1)))` for `n` same-source stories
published that day. It is a stable property of a story's context rather than of
a batch, but the day's output is not known until the day closes, so it would
need finalising once after the fact. That is why it is the fallback.

## What changes

1. **Migration**: add `quality_score DOUBLE PRECISION` and
   `effective_at TIMESTAMPTZ`; index `(effective_at DESC, id DESC)
   WHERE status = 'published'`. Retire `feed_score` after the reader moves.
2. **`pipeline/ranking.py`**: `Q` from rungs earned; drop evidence, primary,
   corroboration, text, and the variety damper.
3. **`db/generation.py`**: write the key alongside `status = 'published'`.
4. **`db/ranking.py`**: `run_ranking` becomes an explicit recompute.
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
