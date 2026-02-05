# Stage 7 — Mobile App (PWA) + Performance + Scaling Upgrades

Stage 7 makes Curious Now feel like a real app on mobile (installable, fast, offline-friendly) and upgrades backend/infra for scale: caching, job queue semantics, and observability/performance budgets.

Stage numbering follows `design_docs/implementation_plan_overview.md`. Stage 7 is intentionally **non-ML** by default: it focuses on reliability, speed, and user experience.

---

## 1) Scope

### 1.1 In scope (Stage 7)

**User-facing (mobile)**

* Ship a high-quality **PWA** from the existing web app (installable on iOS/Android)
* Offline reading for **Saved** clusters (reading list)
* Smooth navigation and perceived speed improvements (prefetch, skeletons, cached pages)

**Backend/infra**

* Redis-backed response caching (feed + cluster + topic)
* Clear cache invalidation strategy tied to `updated_at`
* Job retry/backoff conventions across all workers (ingestion/processing/enrichment/notifications)
* Monitoring and alerting baseline + performance budgets
* Optional: pgvector-based semantic search (behind a feature flag)

### 1.2 Out of scope (explicitly not Stage 7)

* Native iOS/Android apps (React Native/Flutter) — PWA is the Stage 7 “mobile app” direction
* Push notifications (keep Stage 6 email-first; revisit in later stage)
* Rebuilding clustering/ranking with ML (can be Stage 9+)

---

## 2) Entry criteria (prereqs)

Stage 7 assumes:

1. Stage 5 saves exist (`GET /v1/user/saves`) and cluster pages are usable
2. Stage 2 cluster pages are stable (`GET /v1/clusters/{id}`)
3. Stage 6 notifications work (email-first) — not required for PWA, but required for “app-like” engagement loops

---

## 3) Resolved defaults (no blockers)

To avoid decisions blocking implementation, Stage 7 v0 defaults are locked here:

1. **Mobile direction:** PWA on top of the existing web app (no separate native repo).
2. **Cache layer:** Redis (required in Stage 7).
3. **Job queue semantics:** keep jobs idempotent and retry-safe; implementation may be either:
   * Redis queue (recommended at scale), and/or
   * Postgres-backed “queue tables” where already present (e.g., `notification_jobs`).
4. **Observability:** OpenTelemetry-style structured logs + metrics; alert on ingestion failures, queue backlog, and API p95 latency.
5. **Semantic search (optional):** pgvector in Postgres (no separate search cluster), dimension default `1536`.

---

## 4) PWA requirements (mobile app deliverable)

### 4.1 Installable PWA

* Web app ships:
  * `manifest.json` with icons + theme colors
  * Service worker for offline caching
  * “Add to Home Screen” guidance (non-intrusive)

### 4.2 Offline reading list (Saved)

User story:

* “I save a cluster and can open it later with no connection.”

Rules:

* Only **Saved** clusters are cached for offline by default (avoid huge storage).
* Offline content is **the last fetched cluster payload** (no new fetch when offline).
* Evidence links remain clickable (but obviously require network).

Implementation recommendation:

* Cache `GET /v1/clusters/{id}` responses for saved clusters.
* Cache `GET /v1/user/saves` list to render the Saved screen offline.
* Use a size cap (e.g., 50 saved clusters cached; evict LRU).

### 4.3 Performance budgets (client)

Targets (mobile mid-tier device on LTE):

* Feed first render: < 2.0s (p75)
* Cluster page: < 1.5s perceived (skeleton + cached fetch)
* Offline open of a saved cluster: < 300ms

---

## 5) Backend caching (Redis)

### 5.1 What to cache

Cache the most expensive/high-QPS endpoints:

* `GET /v1/feed` (keyed by tab/topic_id/content_type/page/page_size + user_id for `for_you`)
* `GET /v1/clusters/{id}` (public response; user-specific overlays like `is_saved` are per-user)
* `GET /v1/topics/{id}`
* `GET /v1/search?q=...` (optional; short TTL)

### 5.2 Cache keys (v0)

Suggested key format:

* `feed:{tab}:{topic_id}:{content_type}:{page}:{page_size}:{user_id_or_anon}`
* `cluster:{cluster_id}:v{cluster_updated_at_unix}`
* `topic:{topic_id}:v{topic_updated_at_unix}`
* `search:{sha256(q)}`

### 5.3 Invalidation strategy (no guesswork)

* Feed caches:
  * short TTL (e.g., 30–120s)
  * acceptable to be slightly stale
* Cluster/topic caches:
  * versioned by `updated_at` (cache key includes version)
  * no explicit invalidation required; new version naturally misses cache

### 5.4 HTTP caching

Also add HTTP cache support:

* `ETag` for `GET /v1/clusters/{id}` and `GET /v1/topics/{id}` based on `{id}:{updated_at}`
* `Cache-Control: private` for user-personalized responses

---

## 6) Job queue semantics (retries/backoff; idempotency)

Stage 7 does not force a single queue implementation, but it does lock the semantics:

1. **Every job type must be idempotent.**
2. **Retries must not corrupt state.**
3. **Backoff defaults:** exponential with jitter; cap at 30 minutes.
4. **Dead-letter:** after N attempts (default 10), mark as failed and alert.

Where to enforce idempotency:

* ingestion: `items.canonical_hash` unique constraint
* clustering: `cluster_items` primary key
* notifications: `notification_jobs.dedupe_key` unique constraint

---

## 7) Optional semantic search (pgvector)

If you want semantic search without a separate service, enable pgvector and add embedding tables.

Concrete optional migration:

* `design_docs/migrations/2026_02_03_0600_stage7_vector_search_pgvector.sql`

Default embedding source text:

* `story_clusters.canonical_title`
* plus (if available): a short concatenation of `summary_intuition` + `takeaway` (only when present)

Hybrid search (recommended):

* Run Postgres full-text search first for lexical matches.
* Re-rank the top N results using vector similarity.

---

## 8) Observability + performance budgets (server)

### 8.1 API budgets

Targets:

* `GET /v1/feed` p95 < 300ms (cached), < 800ms (uncached)
* `GET /v1/clusters/{id}` p95 < 250ms (cached), < 700ms (uncached)

### 8.2 Alerts (must-have)

* ingestion error streak spikes
* clustering job backlog growing
* notification send failure rate > 5% over 15 minutes
* DB connection saturation

---

## 9) Remaining blockers requiring your decision

None for the roadmap as written (Stage 7 defaults are resolved in §3).

