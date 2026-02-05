# Curious Now — Ops Runbook (Dev → Prod)

This runbook is the “how to run it” layer that complements the design docs, so a developer can ship without guessing execution order, schedules, or config.

---

## 1) Processes (logical services)

Minimum set:

1. **API server**
   * Serves `/v1/*` endpoints (Stage 1+).
2. **Ingestion worker**
   * Fetches RSS/Atom/API feeds on a schedule and upserts Items (Stage 1).
3. **Processing worker**
   * Stage 2: clustering + search-doc updates + trending + topic tagging
   * Stage 3: enrichment (understanding fields + citations) + glossary linking
   * Stage 4: revision snapshots + update logs + lineage builder (optional early)

You can run workers as separate processes or one worker process with multiple job types.

---

## 2) Migration order (must be deterministic)

Recommended order:

1. Stage 1 core:
   * `design_docs/migrations/2026_02_03_0100_stage1_core.sql`
2. Stage 2:
   * `design_docs/migrations/2026_01_29_0201_stage2_clusters.sql`
   * `design_docs/migrations/2026_01_29_0202_stage2_topics.sql`
   * `design_docs/migrations/2026_01_29_0203_stage2_search.sql`
   * `design_docs/migrations/2026_02_03_0204_stage2_cluster_redirects.sql`
3. Stage 3:
   * `design_docs/migrations/2026_02_03_0200_stage3_understanding_glossary.sql`
4. Stage 4:
   * `design_docs/migrations/2026_02_03_0300_stage4_updates_lineage.sql`
5. Stage 5:
   * `design_docs/migrations/2026_02_03_0400_stage5_accounts_personalization.sql`
6. Stage 6:
   * `design_docs/migrations/2026_02_03_0500_stage6_notifications_digests.sql`
7. Stage 7 (optional):
   * `design_docs/migrations/2026_02_03_0600_stage7_vector_search_pgvector.sql` (pgvector semantic search)
8. Stage 8:
   * `design_docs/migrations/2026_02_03_0700_stage8_governance_editorial.sql`
9. Stage 9:
   * `design_docs/migrations/2026_02_03_0800_stage9_search_perf.sql`
10. Stage 10:
   * `design_docs/migrations/2026_02_03_0900_stage10_entities_experiments.sql`

---

## 3) Configuration (recommended)

### 3.0 Source pack (seed + ongoing maintenance)

* Maintain a `source_pack.v0.json` file using the format in `design_docs/source_pack_v0.md`.
* Import it via a CLI script or `POST /v1/admin/source_pack/import` (see `design_docs/openapi.v0.yaml`).

### 3.1 Clustering config

* `config/clustering.v0.json` as specified in `design_docs/stage2.md`.

### 3.2 URL normalization

Rules are locked in `design_docs/decisions.md` and specified concretely in `design_docs/url_normalization_v0.md`.

Implementation recommendation:

* A single library/module used by both the ingestion worker and any admin tooling.
* Per-source overrides in a config file (e.g., `config/url_normalization_overrides.v0.json`; format: `design_docs/url_normalization_v0.md`).

---

## 4) Schedules (recommended starting point)

### 4.1 Ingestion worker

* Every 5 minutes: fetch feeds that are “due” (`last_fetched_at + fetch_interval_minutes`).

### 4.2 Processing worker (Stage 2)

* Continuous (or every 1–5 minutes):
  * “assign clusters for new Items since last run”
  * update `cluster_search_docs` for changed clusters
* Every 10 minutes:
  * recompute trending metrics (`velocity_*`, `distinct_source_count`, `trending_score`)
* Every 30–60 minutes:
  * topic tagging refresh/backfill (if incremental tagging isn’t perfect yet)

### 4.3 Enrichment worker (Stage 3)

* Continuous:
  * enrich clusters that gained meaningful evidence
* Rate-limit/queue this job (it can be the most expensive step).

### 4.4 Updates/lineage (Stage 4)

* On meaningful cluster changes:
  * snapshot revision + create update log entry
* Lineage:
  * daily batch to start; expand later

### 4.5 Notifications/digests (Stage 6)

* Continuous:
  * send due `notification_jobs` (email worker)
* Every 5–15 minutes:
  * enqueue due topic digests
  * enqueue story-update alerts (if not event-driven)

---

## 5) Environment variables (suggested minimal set)

* `DATABASE_URL` (Postgres connection string)
* `PORT` (API server)
* `ADMIN_TOKEN` (protect admin endpoints if implemented)
* `USER_AGENT` (polite UA string for feed fetches)
* `LOG_LEVEL`
* `ENV` (`dev` | `prod`)

Stage 5 auth (recommended defaults; see `design_docs/stage5.md`):

* `APP_BASE_URL` (used to generate magic-link URLs)
* `AUTH_EMAIL_FROM` (sender address, e.g. `Curious Now <no-reply@yourdomain>`; in dev you can omit and log links)
* `POSTMARK_SERVER_TOKEN` (recommended v0 provider; omit in dev to log links instead)

If you use a job queue:

* `REDIS_URL` (Stage 7+ required for Redis caching/queues; optional earlier)

---

## 6) Operational safety (must-have)

* Ingestion must be idempotent via `canonical_hash` (see `design_docs/decisions.md`).
* Workers must be safe under overlap (a second run starting before the first ends).
* Log feed errors and surface `error_streak` in `/v1/sources`.
* For clustering:
  * log assignment decisions (`cluster_assignment_logs`)
  * support cluster quarantine (`story_clusters.status = quarantined`)

---

## 7) Source policy reminders

* Do not store or display paywalled full text by default.
* Only store richer text for sources explicitly whitelisted (see `design_docs/decisions.md`).

---

## 8) API contract source of truth

* `design_docs/openapi.v0.yaml`
