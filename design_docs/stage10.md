# Stage 10 — Mature Ecosystem (Extensibility + Knowledge Graph + Experimentation)

Stage 10 future-proofs Curious Now so you can keep shipping without rewrites: richer entities, deeper graph exploration, and product experimentation — while preserving core principles (source-first, evidence-backed, anti-hype).

Stage numbering follows `design_docs/implementation_plan_overview.md`. API contract source of truth: `design_docs/openapi.v0.yaml`.

---

## 1) Scope

### 1.1 In scope (Stage 10)

**Richer entity following**

* Entity pages for:
  * authors/people
  * institutions
  * models
  * datasets
  * methods
  * venues (journals/conferences)
* Follow entities (like topics) to power discovery and future digests

**Richer knowledge graph exploration**

* Entity graph edges (evidence-backed), e.g.:
  * paper **authored_by** person
  * person **affiliated_with** institution
  * model **trained_on** dataset
  * method **used_by** model/paper
* Cluster → Entity mapping for navigation (“More from this author/lab/model”)
* Topic pages can optionally surface top entities (later)

**Experimentation + feature flags**

* A/B testing framework (ranking/UX variants) with deterministic assignments
* Feature flags with server-side evaluation

**Client polish**

* Deep links that are stable and shareable (`/c/{cluster_id}`, `/t/{topic_id}`, `/e/{entity_id}`)
* Accessibility hardening (keyboard nav, contrast, readable typography defaults)
* Widgets/shortcuts (later; built on stable deep links)

### 1.2 Out of scope (explicitly not Stage 10)

* Open-ended public editing or “Wikipedia mode”
* External search clusters (Elastic/OpenSearch) — Postgres-first remains default
* Social network features (comments, follows-as-feed)

---

## 2) Entry criteria (prereqs)

Stage 10 assumes:

1. Stage 2 clusters + topics exist
2. Stage 4 lineage exists (papers/models graph)
3. Stage 5 accounts exist (for entity follows and experiments tied to users)
4. Stage 8 editorial tooling exists (audit logs + safe overrides)

---

## 3) Resolved defaults (no blockers)

To avoid “we must decide X” blockers, Stage 10 v0 defaults are locked here:

1. **Entity types (v0):** `person`, `institution`, `model`, `dataset`, `method`, `venue`.
2. **Entity data policy:** metadata-first; do not scrape arbitrary pages to build entity bios (same spirit as `design_docs/decisions.md`).
3. **Evidence rule:** entity edges that imply a factual relationship must be evidence-backed (`evidence_item_ids` non-empty).
4. **Experimentation scope:** server-side A/B tests only; assignment is deterministic by user (or client id), stored for consistency.
5. **Feature flags:** evaluated server-side; safe defaults when missing.

---

## 4) Data model (Stage 10)

Concrete SQL migration:

* `design_docs/migrations/2026_02_03_0900_stage10_entities_experiments.sql`

Adds:

* `entities`, `entity_aliases`, `entity_redirects`
* `cluster_entities` (cluster ↔ entity mapping; supports editor locks)
* `entity_edges` (evidence-backed relationships)
* `user_entity_follows`
* `experiments`, `experiment_variants`, `experiment_assignments`
* `feature_flags`

---

## 5) API additions (Stage 10)

Defined in `design_docs/openapi.v0.yaml`:

**Entities**

* `GET /v1/entities?q=...` (search/list entities)
* `GET /v1/entities/{id}` (entity page; 301 if merged)
* `POST /v1/user/follows/entities/{entity_id}`
* `DELETE /v1/user/follows/entities/{entity_id}`
* `GET /v1/user/follows/entities` (optional convenience list)

**Admin (governance + experiments)**

* `POST /v1/admin/entities`, `PATCH /v1/admin/entities/{id}`, `POST /v1/admin/entities/{id}/merge`
* `PUT /v1/admin/clusters/{id}/entities` (manual cluster→entity mapping + locks)
* `POST /v1/admin/experiments`, `PATCH /v1/admin/experiments/{id}`
* `PUT /v1/admin/feature_flags/{key}`

---

## 6) Entity extraction (v0, implementable without scraping)

Stage 10 should not be blocked on full-text access. v0 extraction defaults:

* From preprint/paper metadata (arXiv/Crossref/PubMed when available):
  * authors → `person`
  * journal/conference → `venue`
  * dataset/model/method mentions only when structured metadata exists or curated mapping exists
* From curated allowlists:
  * known labs/institutions
  * known models/datasets
* From editorial actions (Stage 8 admin):
  * admin can create/merge entities and assign them to clusters with `locked=true`

---

## 7) Experimentation framework (v0)

### 7.1 Assignment rules

* Assignment subject:
  * `user` (preferred) when logged in
  * `client` (uuid cookie) for anonymous experiments (optional but supported)
* Deterministic assignment:
  * hash `(experiment_key, subject_id)` → variant bucket
* Persist assignment in `experiment_assignments` so results are stable.

### 7.2 Where experiments apply (examples)

* Feed ranking tweaks (Trending v3 vs v2)
* UI presentation (card density, default tab)
* Digest formatting

---

## 8) Remaining blockers requiring your decision

None for the roadmap as written (Stage 10 defaults are resolved in §3).

