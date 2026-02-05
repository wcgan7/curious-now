# Curious Now — Resolved Decisions (v0)

This doc locks the default choices that unblock later stages. It is designed to remove “we must decide X before Y” blockers while staying conservative on policy and implementation complexity.

If you want to change any of these later, treat this file as the source of truth and update downstream docs accordingly.

---

## 1) Data/IDs (resolved)

**Decision:** Use **Postgres UUIDs** for all primary keys and foreign keys.

* Use `pgcrypto` + `gen_random_uuid()` for defaults.
* Keep timestamps as `timestamptz` in UTC.

Why: simplest, consistent across services, matches Stage 2 migrations.

---

## 2) Text storage + licensing policy (resolved)

**Decision:** Default to **metadata-first** storage, with a conservative allowlist for richer text.

### 2.1 What we store by default (all sources)

* Always store: `title`, `canonical_url`, `published_at`, `source_id`, `content_type`
* Store `snippet` only if it is provided by the feed/API and allowed by the source’s terms.
* Retain raw feed entry JSON for debugging where feasible (`raw_ref` or a raw table/object store pointer).

### 2.2 What we do NOT do by default

* Do **not** scrape and store full article bodies from the open web by default.
* Do **not** store or display paywalled full text.

### 2.3 Allowed richer text sources (recommended)

* For **preprints/papers** (arXiv, bioRxiv, journal APIs): store **abstract** and identifiers (DOI/arXiv/PMID) when available.
* For **press releases/institutional** sources: allow full text **only if explicitly whitelisted** (robots/ToS-compatible).

### 2.4 Stage 3/4 consequence (quality guardrail)

Stage 3 “understanding” summaries are only generated when a cluster has **sufficient accessible primary text**, e.g.:

* a paper/preprint abstract, or
* a whitelisted full-text source, or
* a high-quality excerpt explicitly permitted by the source.

Otherwise, the UI falls back to **evidence-only** (coverage list) plus conservative labeling (preprint disclaimers, anti-hype flags when obvious).

Why: avoids legal risk and prevents hallucination-prone summaries from headline-only input.

---

## 3) Canonical URL + idempotency policy (resolved)

**Decision:** Canonical URL normalization is a first-class Stage 1 requirement and must be deterministic.

Default normalization rules:

* Remove URL fragments (`#...`)
* Normalize scheme/host casing
* Strip common tracking params:
  * `utm_*`, `gclid`, `fbclid`, `mc_cid`, `mc_eid`, `ref`, `ref_src`, `cmpid`, `ICID`, `ocid`
* Keep query params that change content (do not blanket-drop all queries)
* Maintain per-source overrides for known patterns (AMP → canonical, etc.)

**Idempotency key:** `canonical_hash = sha256(normalized_canonical_url)` (or an equivalent stable hash).

Why: clustering quality (Stage 2) depends on it; it’s cheaper than fixing later.

---

## 4) Where Stage 3 “understanding” fields live (resolved)

**Decision:** Store Stage 3 fields as **nullable columns on `story_clusters`** (v0 simplicity).

Stage 3 adds (via migration) columns such as:

* `takeaway`, `summary_intuition`, `summary_deep_dive`
* `assumptions`, `limitations`, `what_could_change_this` (json arrays)
* `confidence_band`
* `method_badges`, `anti_hype_flags` (json arrays)

**Citations:** store “supporting evidence” as json arrays of Item IDs per section, e.g.:

* `takeaway_supporting_item_ids`
* `summary_intuition_supporting_item_ids`
* `summary_deep_dive_supporting_item_ids`

Why: minimizes schema complexity while enforcing source-first guardrails.

---

## 5) “Meaningful change” thresholds (resolved)

**Decision:** Stage 4 emits update log entries only for meaningful changes (not every new link).

Meaningful triggers (v0):

* a new `peer_reviewed` Item attaches
* a new `preprint` or `report` Item attaches (optional but recommended as meaningful)
* `confidence_band` changes
* `anti_hype_flags` changes
* `takeaway` or summaries change due to new evidence (not minor phrasing edits)
* cluster merge/split/quarantine/correction

Non-meaningful examples:

* another syndicated repost
* a new news write-up with no new primary evidence

Hard rule:

* no “Previously/Now/Because” diff without explicit `supporting_item_ids`

Why: avoids noisy logs and aligns with future Stage 6 notifications.

---

## 6) Lineage edge rule (resolved)

**Decision:** No lineage edge can exist without explicit evidence.

Minimum requirements:

* `lineage_edges.evidence_item_ids` must contain ≥1 Item ID
* `lineage_nodes.external_ids` should be stored when available (DOI/arXiv/PMID)
* Auto-detected edges are allowed only if they can cite evidence; otherwise log them as candidates for review but do not persist them as edges

Why: trust collapses quickly if the graph contains “made up” relationships.

---

## 7) Remaining blockers needing your decision

None for the current roadmap as written.
