# Stage 4 — Update Tracking (“What Changed”) + Lineage Timelines

Stage 4 turns StoryClusters into living objects: readers can see **what changed over time** and how ideas connect in a **lineage timeline/graph**.

This doc assumes Stage 2 (clusters) and Stage 3 (structured understanding fields) exist. Locked cross-stage decisions are in `design_docs/decisions.md`. Stage numbering follows `design_docs/implementation_plan_overview.md`.

---

## 1) Scope

### 1.1 In scope (Stage 4)

**User-facing**

* StoryCluster update log (“Updated on YYYY-MM-DD because …”)
* Diff-style explanation: **Previously → Now → Because** (with citations)
* Basic lineage view on Topic pages (timeline/graph) for supported nodes
* (Optional) “Follow story” UI stub (true follow/notifications are later)

**Backend**

* Cluster revision snapshots (versioning)
* “Meaningful change” detector + change summarizer (must cite evidence)
* Lineage graph model (nodes + edges) with evidence requirements

### 1.2 Out of scope (explicitly not Stage 4)

* **Stage 5:** accounts + personalization (persistent follows/saves/blocks)
* **Stage 6:** notifications/digests (delivery + scheduling + quiet hours)
* Heavy editorial tooling (Stage 8) beyond minimal safety overrides

---

## 2) Stage 4 entry criteria (prereqs)

Stage 4 depends on:

1. **Stage 2 is stable**
   * clusters are canonical and not constantly reshuffling
   * clusters have reliable `updated_at`, evidence lists, and content-type labels
2. **Stage 3 writes structured fields (not one blob)**
   * at minimum: `takeaway`, `summary_intuition`, `summary_deep_dive`
   * plus: `confidence_band`, `anti_hype_flags`, `method_badges` (if available)
3. **Citations exist as data**
   * Stage 3 stores per-section `*_supporting_item_ids` on `story_clusters` (locked in `design_docs/decisions.md`)
   * Stage 4 update log entries always include `supporting_item_ids` (no uncited diffs)
4. **Meaningful change policy exists**
   * locked in `design_docs/decisions.md` (Stage 4 emits updates only for meaningful changes)

If Stage 3 explanations are not structured/cited yet, Stage 4 must fall back to:

* update log entries that only state **new evidence added** (no interpretive diff).

---

## 3) UX requirements (Stage 4)

### 3.1 StoryCluster “What changed” module

On the StoryCluster page, show:

* “Updated on 2026-02-02 because …” (date is absolute)
* 3-part diff (when available):
  * **Previously:** 1–3 bullets
  * **Now:** 1–3 bullets
  * **Because:** 1–3 bullets + evidence links

Rules:

* Never show a diff without evidence links.
* If confidence is low: show a minimal update (“New evidence added”) and link out.

### 3.2 Cluster update log timeline

Show a reverse-chronological list:

* date/time
* change type badge (new evidence / refinement / contradiction / merge / correction)
* short, readable summary (1–2 sentences) + “Details” expand

### 3.3 Topic lineage timeline (v0)

On Topic pages, show a timeline/graph when the topic has enough nodes:

* nodes: papers/models/datasets/methods
* edges: extends / improves / contradicts / replaces-in-some-settings / orthogonal
* each edge must link to evidence Items

Stage 4 can start with:

* a small set of supported topics (e.g., AI/ML) where lineage is clear, and expand later.

---

## 4) Data model (implemented)

Concrete SQL migration: `design_docs/migrations/2026_02_03_0300_stage4_updates_lineage.sql`.

### 4.1 Cluster versioning

Store snapshots so you can render diffs even after the live cluster changes.

**`cluster_revisions`**

* `id` (pk, uuid)
* `cluster_id` (fk → story_clusters)
* `created_at`
* `trigger` (enum: `new_item`, `merge`, `split`, `quarantine`, `unquarantine`, `manual_override`, `correction`)
* snapshot fields (copy from cluster at the time):
  * `takeaway`
  * `summary_intuition`
  * `summary_deep_dive`
  * `confidence_band`
  * `method_badges` (jsonb)
  * `anti_hype_flags` (jsonb)
  * `topics` (optional snapshot)
  * `evidence_item_ids` (jsonb array) (optional: “top evidence at the time”)

**`update_log_entries`**

* `id` (pk, uuid)
* `cluster_id` (fk → story_clusters)
* `created_at`
* `change_type` (enum: `new_evidence`, `refinement`, `contradiction`, `merge`, `split`, `quarantine`, `unquarantine`, `correction`)
* `previous_revision_id` (fk)
* `new_revision_id` (fk)
* `summary` (text, 1–2 sentences)
* `diff` (jsonb)
  * `previously` (string[])
  * `now` (string[])
  * `because` (string[])
* `supporting_item_ids` (jsonb array)

Indexes:

* `(cluster_id, created_at DESC)`

### 4.2 Lineage graph

Early constraint (non-negotiable):

* **No lineage edge without explicit evidence** (specific Items or external IDs).

**`lineage_nodes`**

* `id` (pk, uuid)
* `node_type` (enum: `paper`, `model`, `dataset`, `method`)
* `title` (text)
* `external_url` (text)
* `published_at` (timestamptz nullable)
* `external_ids` (jsonb: doi/arxiv/…)
* `topic_ids` (jsonb array; or a join table if you prefer)

**`lineage_edges`**

* `id` (pk, uuid)
* `from_node_id` (fk)
* `to_node_id` (fk)
* `relation_type` (enum: `extends`, `improves`, `compresses`, `replaces_in_some_settings`, `contradicts`, `orthogonal`)
* `evidence_item_ids` (jsonb array)
* `notes_short` (text nullable)

---

## 5) Jobs (Stage 4)

### 5.1 Revision snapshot job

Trigger:

* when Stage 3 enrichment writes/updates structured cluster fields, or
* when a merge/split/quarantine/unquarantine/correction occurs

Steps:

1. decide if the change is “meaningful” (see §6)
2. write a new `cluster_revisions` row
3. if meaningful, create an `update_log_entries` row referencing the previous revision

### 5.2 Change summarizer job

Input:

* previous revision snapshot
* new revision snapshot
* new evidence Items (and their content types/external IDs)

Output:

* `update_log_entries.summary`
* `update_log_entries.diff` (Previously/Now/Because)
* `supporting_item_ids`

Hard rule:

* every “Because” bullet must cite at least one Item ID.

Fallback:

* if citations can’t be produced safely, emit `change_type = new_evidence` with a minimal summary.

### 5.3 Lineage builder job (v0)

Start with a hybrid approach:

* deterministic extraction of nodes from external IDs (DOI/arXiv)
* limited relationship detection based on explicit text patterns or curated mappings
* allow manual overrides later (Stage 8)

---

## 6) “Meaningful change” rules (v0, locked)

These rules are locked in `design_docs/decisions.md` and must be reused again in Stage 6 notifications.

Meaningful triggers (v0):

* a new `peer_reviewed` Item attaches
* a new `preprint` or `report` Item attaches (recommended as meaningful)
* `confidence_band` changes (early → growing → established)
* `anti_hype_flags` changes
* summaries change due to new evidence (not minor phrasing edits)
* cluster merge/split/quarantine/unquarantine/correction

Non-meaningful examples:

* another syndicated repost
* a new news write-up with no new primary evidence

---

## 7) API additions (Stage 4)

* `GET /v1/clusters/{id}/updates`
  * returns update log entries (paged)
* `GET /v1/topics/{id}/lineage`
  * returns lineage nodes + edges for the topic (or a curated subset)

Stage 4 keeps Stage 2 cluster endpoints unchanged; it adds update/lineage endpoints.

---

## 8) Remaining blockers requiring product decisions

None for the roadmap as written. Cross-stage decisions are locked in `design_docs/decisions.md`.
