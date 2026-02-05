# Stage 9 — Platform Hardening + Search/Ranking Upgrades

Stage 9 is about making Curious Now production-grade: reliable ingestion, predictable performance, safer operations, and better retrieval/ranking — without changing the product’s core principles (source-first, evidence-backed, anti-hype).

Stage numbering follows `design_docs/implementation_plan_overview.md`. API contract source of truth remains `design_docs/openapi.v0.yaml` (Stage 9 mostly improves behavior behind existing endpoints).

---

## 1) Scope

### 1.1 In scope (Stage 9)

**Platform hardening**

* SLOs + alerting + incident playbooks
* Backups/restore drills + DB maintenance routines
* Rate limiting + abuse controls + safer admin operations
* Cost controls (caching policies, batching, retention)

**Search upgrades**

* Better lexical ranking (Postgres FTS tuned + stable ordering)
* Fuzzy matching for typos and partial matches (optional `pg_trgm`)
* Hybrid search re-ranking when pgvector is enabled (Stage 7 optional)

**Feed ranking upgrades**

* Trending score v2 (more stable, less gameable)
* For You ranking v2 (still explainable; diversity constraints)

### 1.2 Out of scope (explicitly not Stage 9)

* Rebuilding the system around external search infra (Elastic/OpenSearch) — stay Postgres-first for v0/v1
* “Black box” ML ranking/notification targeting

---

## 2) Entry criteria (prereqs)

Stage 9 assumes:

1. Stage 1–2 are stable (ingestion + clusters)
2. Stage 7 Redis caching is available (recommended; required for scale)
3. Optional: Stage 7 pgvector is enabled if you want hybrid semantic re-ranking

---

## 3) Resolved defaults (no blockers)

To avoid Stage 9 being blocked on infra/product choices, v0 defaults are locked here:

1. **Search infra:** Postgres full-text search is the default; `pg_trgm` is optional but recommended.
2. **Hybrid search:** if pgvector is available, use it only for **re-ranking top N**, not as the only retrieval system.
3. **Caching:** Redis is required; feed caches are short TTL, cluster/topic caches are versioned by `updated_at`.
4. **Retention:** keep high-volume logs/events for **90 days** by default (configurable).
5. **Operational model:** “safe by default” admin actions with audit logging (Stage 8) and no silent destructive actions.

---

## 4) Search upgrades (Stage 9)

### 4.1 Query parsing rules (v0)

* If the query looks like an identifier:
  * arXiv id (e.g., `2401.12345`) → match `items.arxiv_id` first
  * DOI-like (`10.` prefix) → match `items.doi` first
* Else:
  * tokenize and run Postgres FTS against `cluster_search_docs.search_tsv`
  * treat short tokens (<3) as optional (avoid noisy matches)

### 4.2 Ranking (FTS v2)

Use Postgres ranking with stable tie-breakers:

* `rank = ts_rank_cd(search_tsv, query)`
* Add small boosts:
  * `+ idMatchBoost` if DOI/arXiv matches appear in cluster evidence
  * `+ recencyBoost` based on `story_clusters.updated_at`
  * `+ diversityBoost` based on `distinct_source_count` (capped)

Stable ordering:

* order by `rank desc`, then `updated_at desc`, then `cluster_id`

### 4.3 Better “did you mean” / fuzzy (optional `pg_trgm`)

If `pg_trgm` is enabled:

* If FTS returns <K results (default 5), run trigram similarity on `cluster_search_docs.search_text`.
* Use this only as a fallback to avoid expensive fuzzy searches on every query.

Concrete migration (core perf indexes + best-effort `pg_trgm`): `design_docs/migrations/2026_02_03_0800_stage9_search_perf.sql`.

### 4.4 Search text composition (upgrade)

Keep Stage 2 rules, but add safe extra text:

* canonical title
* top N evidence titles
* external IDs (arXiv/DOI/PMID)
* topic names (and aliases)
* Stage 3 fields when present: `takeaway` and `summary_intuition` (already citation-guarded)

Hard rule:

* do not add scraped/paywalled full text (see `design_docs/decisions.md`)

---

## 5) Feed ranking upgrades (Stage 9)

### 5.1 Trending v2 (less jumpy, more trustworthy)

Goal: “Trending” should surface real developments, not syndication storms.

Inputs:

* `velocity_6h`, `velocity_24h`
* `distinct_source_count`
* primary evidence presence (cluster contains `peer_reviewed`/`preprint`/`report`)
* penalties for low-signal patterns (single-source, press-release-only)

Example score:

```
trend =
  0.45 * log1p(velocity_6h) +
  0.25 * log1p(velocity_24h) +
  0.20 * log1p(distinct_source_count) +
  0.10 * primaryEvidenceBoost -
  0.10 * lowSignalPenalty
```

Apply diversity constraints after scoring:

* avoid front-page dominance by a single topic (cap per topic)
* avoid dominance by a single source type

### 5.2 For You v2 (explainable + diverse)

Keep Stage 5’s rules-based approach but add:

* “recently interacted topics” boost (from `engagement_events`)
* diversity caps (per topic and per day)
* explicit exclusions:
  * hidden clusters are never returned
  * clusters with no remaining evidence after source blocks are excluded

---

## 6) Operational hardening (Stage 9)

### 6.1 SLOs (targets)

* Ingestion freshness: 95% of active feeds fetched successfully within their interval * 2
* API latency:
  * `GET /v1/feed` p95 < 300ms cached, < 800ms uncached
  * `GET /v1/clusters/{id}` p95 < 250ms cached, < 700ms uncached
* Notification delivery (email): 99% of jobs sent within 30 minutes outside quiet hours

### 6.2 Alerts (minimum set)

* feed error streak spikes (by feed + by domain)
* processing backlog (new items unclustered > threshold)
* DB disk growth / connection saturation
* API p95 latency regression
* notification send failure rate > 5% over 15 minutes

### 6.3 Backups + restore drill

* nightly automated backups
* weekly restore drill in staging (documented)
* migration rollback plan for every schema change (at least “restore from backup”)

### 6.4 Retention (v0 defaults)

* `engagement_events`: keep 90 days (purge older)
* `feed_fetch_logs`: keep 90 days (purge older)
* `notification_jobs`: keep 90 days after `sent_at` (purge older)
* Keep clusters/items indefinitely (core product history)

---

## 7) Security hardening (Stage 9)

* Enforce strict rate limits on auth endpoints and public read endpoints.
* Ensure session cookies are:
  * `httpOnly`, `secure` (prod), `sameSite=Lax` (v0)
* Admin endpoints:
  * require `X-Admin-Token`
  * log actions in `editorial_actions` when they mutate state (Stage 8)
* Protect against SSRF in feed fetching (allowlist schemes, block internal IP ranges).

---

## 8) Remaining blockers requiring your decision

None for the roadmap as written (Stage 9 defaults are resolved in §3).
