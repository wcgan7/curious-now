# Curious Now v2 — Ranking without a ranking pass

## The problem

113 of 168 published stories sit at `feed_score = 0`, every one of them
published since `run_ranking` last ran. `run_ranking` has one caller and nothing
invokes it after generation.

Scheduling it after generation would fix today's symptom and not the cause. The
score is 35% freshness on an 18-hour half-life, so a stored value is wrong
within hours of being written. Running the pass more often shortens the window
in which the feed is wrong; it does not close it.

There is a second defect in the same number. The variety damper multiplies a
story's score by `0.45 ** repetition`, where `repetition` counts same-source
stories **in that ranking pass**. Two stories of identical merit therefore
receive different permanent scores depending on which batch they were ranked
in. That is not a property of a story.

## The key idea

Combine quality and freshness by multiplication rather than addition, and the
ordering becomes computable once and correct forever.

With `score = Q · exp(-(now - t) / h)` for quality `Q`, publication time `t` and
half-life `h`, take logarithms and multiply by `h`:

```
h · ln(score)  =  h · ln Q  −  now  +  t
               =  (t + h · ln Q)  −  now
                                    ^^^^^ identical for every story
```

The time term is common to all stories, so it cancels out of any comparison.
**`t + h · ln Q` is a sort key that never needs recomputing.**

It has a reading that operators can hold in their heads: a story ranks *as if
published earlier* by an amount its quality earns it. At `h = 18h`, a story of
half quality behaves as though it were 12.5 hours older; the weakest story in
the corpus behaves as though it were 41 hours older.

Because the key is a time, it is stored as one:

```
effective_at = COALESCE(published_at, created_at) + (h · ln Q) hours
ORDER BY effective_at DESC, id DESC
```

The equivalence was checked over 400 synthetic stories at horizons from one
hour to five years, and it holds exactly — with one instructive exception.
Beyond about **532 days** the live score underflows: `exp(-age/h)` reaches
`0.0` in double precision at an age of 709 half-lives, so every older story
scores exactly zero and ties with every other. Working in log space has no such
limit. The stored key is therefore not merely equivalent to the live
computation but strictly better behaved than it.

For contrast, the current additive score was checked the same way: **12 of its
top 12 positions change after a month**. The drift is not a rounding detail.

## Quality

`Q` keeps the existing intrinsic components and their relative weights,
renormalised over the 0.65 that is not freshness:

| Component | Current weight | Renormalised |
| --- | --- | --- |
| Evidence quality | 0.25 | 0.385 |
| Primary availability | 0.15 | 0.231 |
| Corroboration | 0.15 | 0.231 |
| Text sufficiency | 0.10 | 0.154 |

An arithmetic weighted mean is kept rather than a geometric one. A product
would be zeroed by either `primary_availability` or `corroboration`, both of
which legitimately reach 0.0, and a geometric mean would need arbitrary floors
to avoid it. The arithmetic mean cannot reach zero on its own: the existing
tables floor evidence at 0.2 and text at 0.15, so **`Q ≥ 0.1`** and
`h · ln Q ∈ [−41h, 0]`.

Nothing about `Q` refers to another story or to the clock. It is a pure
function of the story, which is what makes the whole scheme work.

## Where it is computed

At publication, in the gate — `_store` is already the only writer of
`status = 'published'`, so computing the key there gives every published story
one, exactly once, with no pass to schedule and nothing to go stale.

`run_ranking` stops being a periodic job. It stays as a **recompute** command
for the one case that genuinely needs it: a change to the weights or the
half-life, which invalidates every stored key at once. That is a deliberate,
infrequent operator action, not a cron.

## Variety, honestly

The damper cannot stay in the score, because it makes the score depend on
batching. Removing it leaves a real problem unsolved: the corpus has
source-days of up to 10 published stories, so a bulk arXiv drop can occupy half
a page.

**Phase one removes it and does nothing else.** The feed will clump. At 168
published stories and a worst case of 10 from one source in a day, that is
visible but not disabling, and it is worth seeing the real shape before
designing against a guess.

**Phase two diversifies at assembly**, not in the score: paginate by
`effective_at` so each story falls on exactly one page, then interleave by
source *within* the page. The page boundary stays keyset-stable while the
reading order inside it spreads sources out.

If clumping proves worse than per-page interleaving can absorb — likely at a
much larger corpus — the escalation is **source-day density**: shift
`effective_at` back by `h · ln(1 / (1 + λ(n − 1)))` where `n` is the number of
same-source stories published that day. That is a stable property of a story's
context rather than of a batch. It carries one wrinkle worth stating now: the
day's output is not fully known until the day closes, so it would need
finalising once, after the fact, reintroducing a small periodic job. That is
the reason it is the fallback rather than the plan.

## What changes

1. **Migration**: add `quality_score DOUBLE PRECISION` and
   `effective_at TIMESTAMPTZ` to `stories`; index
   `(effective_at DESC, id DESC) WHERE status = 'published'`. Keep
   `ranking_reasons`. Retire `feed_score` only after the reader has moved.
2. **`pipeline/ranking.py`**: `score_story` returns `Q` and the offset;
   `rank_stories` loses the variety damper and becomes a plain map.
3. **`db/publication.py`**: compute and write the key as a story is published.
4. **`db/ranking.py`**: `run_ranking` becomes an explicit recompute over all
   published stories.
5. **`apps/reader/lib/data.ts`**: order and paginate on
   `(effective_at, id)` instead of `(feed_score, published_at, id)`.
6. **Backfill**: one recompute for the 168 stories already published.

## What this costs

**Old stories never resurface.** Under the current additive score, freshness
decays toward zero for everything, so ordering drifts toward quality alone and
a good old story climbs back. Under a product, the ordering fixed at
publication is permanent. For a calm feed this is the better behaviour, but it
is a behaviour change and not a refactor.

**A weight change means a full recompute.** Today it happens implicitly on the
next pass. It becomes an explicit command, which is more honest and easier to
get wrong by forgetting.

**Freshness stops being visible in the score.** `quality_score` is intrinsic and
`effective_at` folds the rest in, so "why is this ranked here" is answered by
two numbers rather than one. `ranking_reasons` should record the quality
components and the offset in hours, which reads better than the current list.
