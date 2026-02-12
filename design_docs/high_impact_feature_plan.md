# High Impact Feature Plan (Top 1% Paper Signal)

**Status:** Planning
**Last updated:** 2026-02-10
**Owner:** Stage 3/4 enrichment pipeline

## 1) Objective

Add a high-signal `high_impact` quality that is intentionally rare and calibrated so that only about 1 in 100 eligible papers receive the label.

This should improve prioritization and discovery without adding hype.

## 2) Scope

In scope:

- Paper-centric scoring and labeling (`preprint`, `peer_reviewed`)
- Two-pass scoring (`provisional_score`, `final_score`)
- Top-1% threshold calibration
- API/UI exposure for badge + explanation
- Ops monitoring and recalibration

Out of scope (v1):

- Citation-count based impact modeling
- Author/institution prestige models
- Cross-topic normalization beyond percentile calibration

## 3) Core decisions (locked for v1)

1. We compute **two scores**:
- `provisional_score`: early, before full text/deep-dive is ready
- `final_score`: after full-text/deep-dive context exists

2. We only assign public `high_impact` label from **final score**.

3. v1 impact model uses only:
- `novelty_score`
- `translation_score`
- `evidence_score`

4. Weight novelty and translation higher:

```
impact_score = 0.45 * novelty_score
             + 0.40 * translation_score
             + 0.15 * evidence_score
```

5. Evidence is also a gate:
- Do not assign `high_impact` unless `evidence_score >= 0.35`.

## 4) Why provisional score exists

`provisional_score` is for routing and operations, not final labeling.

Use cases:

- Prioritize paper text hydration queue
- Prioritize deep-dive generation queue
- Prioritize expensive validation checks
- Provide temporary internal ranking while final score is pending
- Measure provisional vs final drift over time

## 5) Eligibility rules

Only these clusters can receive final high-impact labels:

- Cluster has paper evidence (`preprint` or `peer_reviewed`)
- At least one paper item has usable full text (`full_text` present, non-empty)
- Final score successfully computed

Clusters without full text can still receive `provisional_score` but cannot be labeled high impact.

## 6) Scoring details

All component scores are bounded `[0.0, 1.0]`.

### 6.1 novelty_score

Intent: estimate how non-redundant the work is vs recent topic-neighbor papers.

Suggested signals:

- Embedding distance from recent cluster centroids in same topic
- Presence of new methods/datasets/tasks vs prior lineage nodes
- De-duplication penalty for near-equivalent findings

### 6.2 translation_score

Intent: estimate practical downstream significance.

Suggested signals:

- Structured extraction from takeaway/deep-dive: affected population, time horizon, actionability
- Materiality cues (size of effect, scope, system-level consequences)
- Clear path from finding to real-world change (not just curiosity value)

### 6.3 evidence_score

Intent: capture support quality and reliability.

Suggested signals:

- Peer-reviewed vs preprint mix
- Source independence and count
- Full-text quality sufficiency
- Anti-hype risk flags as penalties (single source, press-release-only, etc.)

## 7) Calibration to top 1%

High-impact must be calibrated, not hardcoded by absolute score.

### 7.1 Population for thresholding

Compute percentiles only over **final-score-eligible** clusters.

### 7.2 Bucketing

Primary bucket:

- Topic x age bucket (`0-30d`, `31-90d`, `91-365d`)

Fallback chain when sample size is too small:

1. Topic x age bucket
2. Age bucket global
3. Global (all eligible clusters)

### 7.3 Threshold

- Use rolling 180-day history
- `threshold = p99(impact_score)` for selected bucket
- Label if:
  - `impact_score >= threshold`
  - `evidence_score >= 0.35`
  - `impact_confidence >= 0.75`

### 7.4 Rate guardrail

Monitor labeled fraction weekly:

- Target band: `0.7%` to `1.3%`
- Alert and recalibrate if outside band for 2 consecutive runs

## 8) Data model changes (proposed)

Add fields to `story_clusters`:

- `high_impact_provisional_score DOUBLE PRECISION NULL`
- `high_impact_final_score DOUBLE PRECISION NULL`
- `high_impact_confidence DOUBLE PRECISION NULL`
- `high_impact_label BOOLEAN NOT NULL DEFAULT FALSE`
- `high_impact_reasons JSONB NOT NULL DEFAULT '[]'::jsonb`
- `high_impact_version TEXT NULL`
- `high_impact_assessed_at TIMESTAMPTZ NULL`
- `high_impact_eligible BOOLEAN NOT NULL DEFAULT FALSE`
- `high_impact_threshold_bucket TEXT NULL`
- `high_impact_threshold_value DOUBLE PRECISION NULL`

Optional index:

- Partial index on `(high_impact_label, updated_at DESC)` where `status='active'`

## 9) Pipeline integration plan

### 9.1 Compute provisional score

When:

- After takeaway generation (or whenever minimal context exists)

Where:

- Stage 3 enrichment flow in `curious_now/ai_generation.py`

Behavior:

- Write provisional fields
- Keep label false until final pass

### 9.2 Compute final score and label

When:

- After full-text-backed deep-dive generation path succeeds

Behavior:

- Compute final component scores + confidence
- Resolve percentile threshold
- Apply gating + set `high_impact_label`
- Persist reason codes for explainability

### 9.3 Recompute triggers

- New primary paper item added to cluster
- Full text arrives for previously provisional-only cluster
- Topic assignment changed
- Calibration window recompute job runs

## 10) API and UI plan

Expose on feed/detail models:

- `high_impact_label`
- `high_impact_final_score` (internal/admin only at first)
- `high_impact_reasons`

UI behavior:

- Badge text: `High Impact (Top 1%)`
- Show reasons in trust/evidence section (short labels from reason codes)
- Never show badge when only provisional score exists

## 11) Explainability reason codes (v1)

Store short stable codes, for example:

- `high_novelty_vs_topic`
- `high_translation_scope`
- `peer_reviewed_support`
- `multi_source_independent_support`
- `evidence_gate_passed`

## 12) Rollout plan

1. Ship schema + scoring code behind feature flag (off by default)
2. Backfill final/provisional scores for last 180 days
3. Run shadow mode for 1-2 weeks (compute, do not display label)
4. Validate label rate and precision proxies
5. Enable badge in UI for a limited cohort
6. Full rollout after stability checks

## 13) Validation and testing

Unit tests:

- Score component bounds and weighted combine
- Evidence gate behavior
- Threshold fallback logic

Integration tests:

- Provisional-only cluster does not label
- Full-text cluster can label if above threshold
- Label rate remains in guardrail band on fixture dataset

Regression tests:

- Recompute updates labels deterministically for fixed snapshots

## 14) Implementation checklist

- [ ] Migration for high-impact fields on `story_clusters`
- [ ] New scoring module (e.g. `curious_now/impact_scoring.py`)
- [ ] Add provisional score write path in Stage 3 pipeline
- [ ] Add final score + labeling path after deep-dive/full-text
- [ ] Add calibration job + threshold persistence
- [ ] Add CLI command for backfill/recompute
- [ ] Expose fields in API schemas + repos
- [ ] Add UI badge + reason rendering
- [ ] Add monitoring dashboard and alerts
- [ ] Run shadow rollout and tune thresholds
