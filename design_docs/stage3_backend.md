# Stage 3 — Understanding Layer Backend Spec (Enrichment + Guardrails)

Stage 3 turns StoryClusters from “coverage pages” into “understandable stories” by writing **structured, evidence-backed fields** onto `story_clusters`, plus glossary support.

This doc is backend-focused. The UI spec and component system live in `design_docs/stage3.md`. Locked cross-stage decisions live in `design_docs/decisions.md`.

---

## 1) Scope (Stage 3 backend)

### 1.1 In scope

* Schema migration that adds “understanding fields” + per-section supporting Item IDs to `story_clusters`
* Enrichment job contract (inputs, outputs, safety constraints)
* Glossary schema + minimal resolver workflow
* Quality gates and fallback behavior when text is insufficient

### 1.2 Out of scope

* Update tracking + lineage storage and endpoints (Stage 4; see `design_docs/stage4.md`)
* Accounts/personalization (Stage 5)
* Notifications/digests (Stage 6)

---

## 2) Schema (Stage 3)

Concrete SQL migration: `design_docs/migrations/2026_02_03_0200_stage3_understanding_glossary.sql`.

### 2.1 New/updated fields on `story_clusters`

Stage 3 writes these fields (nullable unless noted). **No section is allowed to exist without citations.**

* `takeaway` (text)
* `takeaway_supporting_item_ids` (jsonb array, default `[]`)
* `summary_intuition` (text)
* `summary_intuition_supporting_item_ids` (jsonb array, default `[]`)
* `summary_deep_dive` (text)
* `summary_deep_dive_supporting_item_ids` (jsonb array, default `[]`)
* `assumptions` (jsonb array, default `[]`)
* `limitations` (jsonb array, default `[]`)
* `what_could_change_this` (jsonb array, default `[]`)
* `confidence_band` (`early` | `growing` | `established`)
* `method_badges` (jsonb array, default `[]`)
* `anti_hype_flags` (jsonb array, default `[]`)

### 2.2 Glossary tables

* `glossary_entries` (term + short/long defs + aliases)
* `cluster_glossary_links` (optional join to precompute what terms appear in a cluster)

---

## 3) Enrichment job contract

### 3.1 Triggering

Run enrichment when:

* a new cluster is created (Stage 2), or
* a cluster receives meaningful new evidence (preprint/report/peer_reviewed; see `design_docs/decisions.md`)

### 3.2 Inputs

Minimum required inputs:

* cluster id
* evidence Items (from `cluster_items` joined to `items` and `sources`)
  * titles, snippets (if permitted), content_type, published_at
  * external IDs (arXiv/DOI/PMID)

Optional but recommended inputs:

* paper abstracts for preprints/papers (per `design_docs/decisions.md`)
* lightweight topic tags (from `cluster_topics`)

#### 3.2.1 v0 “accessible text” defaults (no scraping required)

To avoid blockers and legal risk, Stage 3 v0 can be implemented with a conservative text set:

* Use `items.snippet` only when it was provided by the feed/API and is permitted.
* For `preprint` Items from arXiv-like sources: use the feed/API-provided abstract/summary as the “primary text”.
* Do not fetch or store paywalled article bodies.
* Do not scrape arbitrary webpages for full text by default.

### 3.3 Outputs (DB writes)

The job either writes a fully-cited understanding payload, or writes nothing and marks the cluster as “evidence-only” via empty fields.

If it writes a section (`takeaway`, `summary_intuition`, `summary_deep_dive`), it must also write:

* the matching `*_supporting_item_ids` (non-empty json array)

### 3.4 Safety/guardrails (must implement)

* **No fabrication:** if you only have headlines and no permitted text/abstract, do not infer specifics.
* **Citation requirement:** every section requires supporting Item IDs.
* **Uncertainty-first:** when evidence is early/weak (preprint-only, press-release-only), the output must reflect that via `anti_hype_flags` and (optionally) conservative language.
* **Content-type disclaimers are UI-driven:** Stage 3 must ensure `items.content_type` is correct; UI uses it for banners.

### 3.5 Fallback behavior (“evidence-only mode”)

If insufficient accessible text exists:

* set `takeaway = NULL`, `summary_intuition = NULL`, `summary_deep_dive = NULL`
* set all `*_supporting_item_ids = []`
* keep the cluster page as an evidence list (Stage 2 behavior)

---

## 4) Suggested minimal algorithms (v0)

### 4.1 Choosing “primary evidence”

Prefer evidence Items in this order:

1. `peer_reviewed`
2. `preprint`
3. `report`
4. `press_release`
5. `news`

### 4.2 Confidence band (v0 heuristic)

* `early`: preprint-only or press-release-only, or single-source primary evidence
* `growing`: multiple independent sources, and at least one primary (preprint/report/peer_reviewed)
* `established`: peer-reviewed + multiple independent sources OR repeated confirmations over time

### 4.3 Anti-hype flags (v0 set)

Store as strings in `anti_hype_flags` (expand later):

* `preprint_not_peer_reviewed`
* `press_release_only`
* `single_source`
* `small_sample` (only if evidence explicitly states this)
* `animal_only` (only if evidence explicitly states this)

### 4.4 Method badges (v0 set)

Store as strings in `method_badges`:

* `observational`
* `experiment`
* `simulation`
* `clinical`
* `benchmark`

Only add a badge when supported by an evidence Item (and cite it).

---

## 5) Quality gates (Stage 3)

At minimum, enforce in the enrichment pipeline:

* If any section text is non-null, its supporting Item IDs list must be non-empty.
* If `anti_hype_flags` includes `preprint_not_peer_reviewed`, the cluster must contain at least one `preprint` Item.
* Log enrichment failures and fall back to evidence-only (never crash the worker).

---

## 6) API expectations (Stage 3)

Stage 3 does not add new required public endpoints, but it extends existing responses:

* `GET /v1/clusters/{id}` includes the Stage 3 fields (`takeaway`, `summary_*`, `confidence_band`, `method_badges`, `anti_hype_flags`, `assumptions`, `limitations`, `what_could_change_this`) plus per-section `*_supporting_item_ids`.
* For glossary, v0 uses a cluster-level payload:
  * `GET /v1/clusters/{id}` may include `glossary_entries` (top terms for tooltips).
  * `GET /v1/glossary?term=...` performs server-side lookup by `term` or alias.

These shapes are defined in `design_docs/openapi.v0.yaml`.
