# Stage 8 — Governance + Editorial Tooling (“Trust Flywheel”)

Stage 8 prevents quality collapse as sources and volume grow. It introduces:

* a **feedback → triage → correction** loop,
* safe **editorial overrides** (merge/split/quarantine, topic fixes, lineage fixes),
* a durable **audit trail** so the system is explainable and trustworthy.

This stage assumes the product unit is the **StoryCluster** (Stage 2), meaningful updates exist (Stage 4), and accounts exist (Stage 5). API contract source of truth: `design_docs/openapi.v0.yaml`.

---

## 1) Scope

### 1.1 In scope (Stage 8)

**User-facing**

* “Report an issue” on StoryCluster pages (optional auth)
* Visible “Correction” updates (already supported by Stage 4; Stage 8 adds editorial workflow to produce them reliably)

**Editorial/admin**

* Feedback triage queue (new → triaged → resolved/ignored)
* Safe cluster operations:
  * merge, split, quarantine/unquarantine (with stable redirects + audit log)
  * edit cluster titles + representative items
  * manual corrections to Stage 3 fields (takeaway/summaries/flags) with citations
* Topic governance:
  * create/rename/alias/merge topics (with redirects)
  * fix cluster topic tags and lock them against auto-overwrites
* Lineage governance:
  * add/edit lineage nodes/edges (evidence required; no invented edges)
* Source governance:
  * update `reliability_tier`, pause sources/feeds, document ToS notes (with audit log)

### 1.2 Out of scope (explicitly not Stage 8)

* Full RBAC / multi-role permissions system (v0 uses the existing admin auth gate)
* Public “comment threads” (feedback is a private signal for quality, not a social feature)

---

## 2) Entry criteria (prereqs)

Stage 8 assumes:

1. Stage 2 clusters exist and are stable enough to curate (`story_clusters`, `cluster_items`)
2. Stage 4 update logging exists (`update_log_entries`, `cluster_revisions`)
3. Stage 5 accounts exist (`users`, `user_sessions`, prefs) — feedback can be anonymous, but admin tooling benefits from user IDs

---

## 3) Resolved defaults (no blockers)

To avoid product decisions blocking implementation, Stage 8 v0 defaults are locked here:

1. **Admin auth:** re-use `X-Admin-Token` for all Stage 8 admin endpoints.
2. **Audit trail:** every editorial action writes an `editorial_actions` row.
3. **Corrections policy:** “correction” updates must:
   * cite evidence (`supporting_item_ids`), and
   * create a Stage 4 update log entry (`change_type = correction`).
4. **Topic merges preserve URLs:** merged topics return a redirect response (see OpenAPI) via `topic_redirects`.
5. **Topic tag locks:** any manually edited topic assignment defaults to `locked = true` so auto-tagging can’t overwrite it.

---

## 4) Data model (Stage 8)

Concrete SQL migration:

* `design_docs/migrations/2026_02_03_0700_stage8_governance_editorial.sql`

Adds:

* `feedback_reports` (user/anonymous feedback on clusters/items/topics)
* `editorial_actions` (append-only audit log)
* `topic_redirects` (stable URLs when topics are merged)
* `cluster_topics.assignment_source` + `cluster_topics.locked` (manual topic fixes)

---

## 5) API additions (Stage 8)

Defined in `design_docs/openapi.v0.yaml`:

**Public feedback**

* `POST /v1/feedback` (auth optional)

**Admin governance**

* Feedback triage:
  * `GET /v1/admin/feedback`
  * `PATCH /v1/admin/feedback/{id}`
* Cluster ops:
  * `POST /v1/admin/clusters/{id}/merge`
  * `POST /v1/admin/clusters/{id}/split`
  * `POST /v1/admin/clusters/{id}/quarantine`
  * `POST /v1/admin/clusters/{id}/unquarantine`
  * `PATCH /v1/admin/clusters/{id}` (manual overrides; citations required)
  * `PUT /v1/admin/clusters/{id}/topics` (manual topic assignment + locks)
* Topic ops:
  * `POST /v1/admin/topics`
  * `PATCH /v1/admin/topics/{id}`
  * `POST /v1/admin/topics/{id}/merge`
* Lineage ops:
  * `POST /v1/admin/lineage/nodes`
  * `POST /v1/admin/lineage/edges`

---

## 6) Editorial workflows (implementation-ready)

### 6.1 Feedback → triage → action

1. User submits `POST /v1/feedback` on a cluster (type + optional text).
2. Admin reviews in `GET /v1/admin/feedback?status=new`.
3. Admin either:
   * marks “ignored” (spam/non-actionable), or
   * performs an action (merge/split/correction/topic fix/lineage fix), then marks “resolved”.
4. The action must also create an `editorial_actions` record linking to the feedback id.

### 6.2 Safe cluster merge (preserve links)

When merging **A → B**:

1. Move all `cluster_items` from A into B (dedupe by PK).
2. Recompute B counters (`distinct_source_count`, `item_count`, velocities).
3. Set `story_clusters.status = 'merged'` for A.
4. Insert `cluster_redirects(from_cluster_id=A, to_cluster_id=B)`.
5. Create Stage 4 revision + update log entry:
   * `cluster_revisions.trigger = merge`
   * `update_log_entries.change_type = merge`
   * `supporting_item_ids` references at least one evidence Item (usually an overlapping primary evidence item).
6. Insert an `editorial_actions` row capturing:
   * action type = `merge_cluster`
   * `target_cluster_id = B`
   * payload includes `from_cluster_id = A` and a short reason.

### 6.3 Safe cluster split

Split is “extract items into a new cluster”:

1. Create new cluster C.
2. Move selected `cluster_items` from A to C.
3. Recompute counters for A and C.
4. Create Stage 4 update log entries:
   * on A: `change_type = split` (explains extraction)
   * on C: `change_type = split` (explains origin)
5. Insert an `editorial_actions` row (`split_cluster`) with moved item ids in payload.

### 6.4 Manual corrections to Stage 3 fields (with citations)

When editing `takeaway` / summaries / flags:

* Any non-null section must have non-empty `*_supporting_item_ids`.
* Use Stage 4 to record the change:
  * trigger `correction` when the previous text was wrong/misleading,
  * trigger `manual_override` when it’s an improvement/clarification.

### 6.5 Topic governance (rename/merge)

* Renames update `topics.name` (unique) and optionally add the old name to `topics.aliases`.
* Merging **Topic A → Topic B**:
  1. Move cluster associations:
     * for each `cluster_topics` row of A, upsert `(cluster_id, topic_id=B)` if missing
  2. Create `topic_redirects(from_topic_id=A, to_topic_id=B)`.
  3. Record `editorial_actions` (`merge_topic`).
* `GET /v1/topics/{id}` for a merged topic returns a redirect response.

### 6.6 Topic tag fixes (manual + locked)

Admin sets cluster topics with locks:

* set `cluster_topics.assignment_source = editor`
* set `cluster_topics.locked = true`
* processing auto-tagging must not delete/overwrite locked assignments

### 6.7 Lineage governance (no edges without evidence)

Admin can create lineage nodes and edges, but must supply `evidence_item_ids` (non-empty).

Record `editorial_actions` for each lineage change.

---

## 7) Observability + quality gates (Stage 8)

Track:

* feedback volume (new/triaged/resolved) by week
* merge/split rates (signals clustering drift)
* correction rate by topic/source type

Quality gates:

* No uncited corrections or lineage edges (enforced via API + DB checks where applicable).
* Locked topic tags cannot be overwritten by automation.

---

## 8) Remaining blockers requiring your decision

None for the roadmap as written (Stage 8 defaults are resolved in §3).

