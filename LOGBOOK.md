# Curious Now — Implementation Logbook

This file tracks implementation progress and verification steps against `design_docs/`.

## 2026-02-03

### Kickoff

- Repository initially contained only `design_docs/` (no application code).
- Goal: implement Stages 1–10 as described, keeping docs as source of truth (especially `design_docs/openapi.v0.yaml` and `design_docs/migrations/*.sql`).

### Block 0 — Project scaffolding + tooling

- Added Python service scaffolding under `curious_now/` and a minimal FastAPI app (`/healthz`).
- Added dependency pinning (`requirements.txt`, `requirements-dev.txt`) and lint/type/test config (`ruff.toml`, `pyproject.toml`).
- Created isolated virtualenv `.venv/` and installed deps there (avoid global conda conflicts).
- Added migration runner (`python -m curious_now.cli migrate`) and fixed migration execution mode to use autocommit so SQL files with `BEGIN; ... COMMIT;` can run.

Verification:

- `pytest`, `ruff`, and `mypy` all pass in `.venv/` after fixing minor issues (migration filename regex, env-loading at import time, typing).
- Added docker-compose for Postgres/Redis, but local execution requires a running Docker daemon (Docker Desktop).
- Next: bring up Postgres/Redis for integration testing and implement Stage 1 DB + API.

### Block 1 — Stage 1 API (sources + items + admin source pack)

- Implemented Stage 1 public endpoints:
  - `GET /v1/items/feed`
  - `GET /v1/sources`
- Implemented Stage 1 admin endpoints (token-gated):
  - `POST /v1/admin/source_pack/import`
  - `PATCH /v1/admin/sources/{id}`
  - `PATCH /v1/admin/feeds/{id}`
  - `POST /v1/admin/ingestion/run` (currently returns `queued`; worker wiring pending)

Testing:

- Added a route-registration test to ensure Stage 1 endpoints are present.
- `pytest`, `ruff`, `mypy` are green.
- Integration tests requiring a running Postgres instance remain blocked locally until Docker Desktop / a Postgres server is running.

### Block 2 — Stage 2 API (cluster feed + topics + search)

- Implemented Stage 2 public endpoints:
  - `GET /v1/feed` (latest/trending; `for_you` returns 401 until Stage 5 auth is wired)
  - `GET /v1/clusters/{id}` (returns 301 redirect payload when cluster was merged)
  - `GET /v1/topics`
  - `GET /v1/topics/{id}` (topic detail + cluster lists)
  - `GET /v1/search?q=...` (Postgres FTS against `cluster_search_docs`)

Testing:

- Added route-registration tests for Stage 2 endpoints.
- `pytest`, `ruff`, `mypy` are green.

### Block 2a — Integration tests + fixes (Stage 1–4 read paths)

- Fixed migration ordering: migrations now apply in the deterministic order listed in `design_docs/ops_runbook.md` (needed because filenames are not strictly chronological/stage-ordered).
- Added Postgres-backed integration tests for Stage 1–4 read paths and validated against a real Postgres instance:
  - Stage 1: admin source pack import; `GET /v1/sources`; `GET /v1/items/feed`
  - Stage 2: `GET /v1/feed`, `GET /v1/clusters/{id}`, `GET /v1/topics`, `GET /v1/topics/{id}`, `GET /v1/search`
  - Stage 3: `GET /v1/glossary` + `glossary_entries` in cluster detail via `cluster_glossary_links`
  - Stage 4: `GET /v1/clusters/{id}/updates`, `GET /v1/topics/{id}/lineage`

Notable fixes:

- Stage 1 source pack import: fixed dict-row access for `RETURNING id`.
- Stage 2 content-type badges: normalized Postgres enum-array string format (`{preprint,...}`) into real lists to prevent per-character parsing.

### Block 3 — Stage 5 (auth + prefs + For You + events)

- Implemented magic-link login + session cookies:
  - `POST /v1/auth/magic_link/start` (dev behavior: prints token)
  - `POST /v1/auth/magic_link/verify` (sets `cn_session`)
  - `POST /v1/auth/logout` (revokes session + clears cookie)
- Implemented user state:
  - `GET /v1/user`
  - `GET /v1/user/prefs`, `PATCH /v1/user/prefs`
  - Follow/block/save/hide endpoints
  - `GET /v1/user/saves`
- Implemented `GET /v1/feed?tab=for_you` for authenticated users (simple rules: followed topics OR saved clusters; hides excluded).
- Implemented `POST /v1/events` → `engagement_events` (user attached when session cookie present).

Testing:

- Added Postgres-backed integration test covering login → prefs → follow topic → for_you feed → saves → events.
- Fixed minor row-factory assumptions so repo functions work whether the connection returns dict rows or tuples.

### Block 4 — Stage 6 (watches API)

- Implemented story watch endpoints:
  - `POST /v1/user/watches/clusters/{cluster_id}`
  - `DELETE /v1/user/watches/clusters/{cluster_id}`
  - `GET /v1/user/watches/clusters`
- Extended integration test to cover watch + list watches.

### Block 4a — Test suite sweep (Stage 1–6)

- Re-ran integration tests against the running docker Postgres instance and confirmed Stage 1–6 behaviors remain correct.
- Fixed minor `mypy --strict` issues in route-registration tests (explicitly typed the `methods` local to avoid `var-annotated` errors).

Verification:

- `CN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curious_now CN_ADMIN_TOKEN=test-admin-token pytest -q` → `11 passed`
- `ruff check .` → clean
- `mypy curious_now tests` → clean

### Block 4b — Stage 1–2 API polish

- Enforced OpenAPI pagination constraints in Stage 1–2 routes via FastAPI `Query` validators (`page >= 1`, `1 <= page_size <= 100`).

Verification:

- `CN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curious_now CN_ADMIN_TOKEN=test-admin-token pytest -q` → `11 passed`

### Block 5 — Stage 6 notifications (job queue + dev sender)

- Implemented Stage 6 notification job mechanics in `curious_now/notifications.py`:
  - enqueue cluster-update alert jobs from `update_log_entries` for watchers (deduped, quiet-hours scheduling, daily cap)
  - enqueue topic digest jobs (daily/weekly) for followed topics (deduped per period)
  - dev sender: renders subject/text/html and marks jobs as `sent` (records rendered content on the job row)
- Extended CLI:
  - `python -m curious_now.cli enqueue-notifications`
  - `python -m curious_now.cli send-notifications`
- Aligned `GET /v1/user/prefs` defaults: `notification_settings` is now returned as a merged v0 shape (from `design_docs/stage6.md`), even if DB has an empty/null blob.

Testing:

- Added integration test `tests/test_integration_stage6_notifications.py` validating:
  - cluster-update job enqueue on new `update_log_entries` for watched clusters
  - quiet-hours deferral to the next quiet-end time (UTC in test)
  - dev sender marks jobs as sent

Verification:

- `CN_DATABASE_URL=... pytest -q` → `12 passed`

### Block 6 — Stage 7 backend caching + HTTP ETags

- Added Redis cache helpers in `curious_now/cache.py` (best-effort; disabled if `CN_REDIS_URL` not set).
- Added Redis response caching for:
  - `GET /v1/feed` (TTL 60s; includes user_id in cache key for `for_you`)
  - `GET /v1/clusters/{id}` (versioned key by `updated_at`, TTL 1h)
  - `GET /v1/topics/{id}` (versioned key by `updated_at`, TTL 1h)
  - `GET /v1/search` (TTL 60s; sha256 key)
- Added weak `ETag` support for `GET /v1/clusters/{id}` and `GET /v1/topics/{id}` and returns `304` when `If-None-Match` matches.

Testing:

- Added integration test `tests/test_integration_stage7_cache.py` (skips unless `CN_REDIS_URL` set) verifying:
  - Redis cache hit/miss behavior on cluster detail
  - ETag round-trip and `304` response

Verification:

- `CN_DATABASE_URL=... CN_REDIS_URL=... pytest -q` → `13 passed`

### Block 7 — Stage 8 governance/editorial (feedback + admin ops)

- Added Stage 8 schemas in `curious_now/api/schemas.py` for feedback + admin governance requests/responses.
- Implemented Stage 8 API in `curious_now/api/routes_stage8.py`:
  - `POST /v1/feedback` (auth optional; writes `feedback_reports`)
  - Admin feedback triage: `GET /v1/admin/feedback`, `PATCH /v1/admin/feedback/{id}`
  - Admin cluster ops: merge/split/quarantine/unquarantine, patch cluster, set cluster topics (locks)
  - Admin topic ops: create/patch/merge topics (creates `topic_redirects`)
  - Admin lineage ops: create nodes/edges (evidence required)
- Implemented DB logic + audit logging in `curious_now/repo_stage8.py`:
  - writes `editorial_actions` for every admin action
  - creates `update_log_entries` for merge/split/quarantine/unquarantine/corrections
  - recomputes cluster counters after merges/splits
- Public topic endpoints now respect redirects:
  - `GET /v1/topics/{id}` and `GET /v1/topics/{id}/lineage` return 301 with `redirect_to_topic_id` when merged.

Testing:

- Added route-registration test `tests/test_stage8_routes_present.py`.
- Added integration test `tests/test_integration_stage8_governance.py` covering feedback, topic merge redirect, cluster merge redirect, topic locks, and lineage create.

Verification:

- `CN_DATABASE_URL=... CN_ADMIN_TOKEN=... pytest -q` → `15 passed`

### Block 8 — Stage 9 hardening (rate limits + search upgrades + retention tooling)

- Added Redis-backed rate limiting (`curious_now/rate_limit.py`) and applied it to:
  - `POST /v1/auth/magic_link/start`
  - `POST /v1/auth/magic_link/verify`
  - `POST /v1/feedback`
  - `GET /v1/search`
- Upgraded search behavior (`curious_now/repo_stage2.py`):
  - identifier-first lookup for DOI and arXiv IDs via `items.doi` / `items.arxiv_id`
  - improved FTS ordering with stable tie-breakers
  - best-effort trigram fallback when FTS yields few results (skips if `pg_trgm` isn’t available)
- Added retention helper `curious_now/retention.py` + CLI command:
  - `python -m curious_now.cli purge-logs` (dry-run by default; use `--apply` to delete)
- Tightened OpenAPI-aligned validation for `/v1/search` (`q` min length).

Testing:

- Added integration test `tests/test_integration_stage9_search_ids.py` covering DOI/arXiv identifier-first search.

Verification:

- `CN_DATABASE_URL=... CN_REDIS_URL=... pytest -q` → `16 passed`

### Block 9 — Stage 10 entities + experiments + feature flags

- Updated entity schemas in `curious_now/api/schemas.py` to match `design_docs/openapi.v0.yaml`:
  - `EntitiesResponse` now returns `{page, results}` and entity models include `external_url`
  - `EntityDetail` now returns `{entity fields..., latest_clusters, related_entities}`
  - Added Stage 10 admin schemas for entities, experiments, and feature flags.
- Implemented Stage 10 DB logic in `curious_now/repo_stage10.py`:
  - entity search/list + detail (includes cluster cards and related entities)
  - entity redirects on merge (`entity_redirects`)
  - user entity follows (`user_entity_follows`)
  - admin cluster→entity assignments with locks (`cluster_entities`)
  - experiments + feature flags CRUD (minimal v0)
- Implemented Stage 10 API in `curious_now/api/routes_stage10.py` and wired it into `curious_now/api/app.py`:
  - `GET /v1/entities`, `GET /v1/entities/{id}` (301 on merged entity)
  - `GET/POST/DELETE /v1/user/follows/entities...`
  - admin entity create/patch/merge
  - admin cluster entities set
  - admin experiments create/patch
  - admin feature flag upsert

Testing:

- Added route-registration test `tests/test_stage10_routes_present.py`.
- Added integration test `tests/test_integration_stage10_entities_experiments.py`.

Verification:

- `CN_DATABASE_URL=... CN_ADMIN_TOKEN=... pytest -q` → `18 passed`

### Block 10 — Stage 1 ingestion worker + Stage 2 pipeline jobs

- Implemented Stage 1 ingestion worker in `curious_now/ingestion.py`:
  - fetches RSS/Atom feeds, parses entries, normalizes URLs, extracts arXiv/DOI IDs, and upserts into `items`
  - writes `feed_fetch_logs` and updates `source_feeds` health fields (`last_fetched_at`, `last_status`, `error_streak`)
- Wired `POST /v1/admin/ingestion/run` to execute ingestion as a FastAPI background task (best-effort).
- Extended CLI (`curious_now/cli.py`) with worker commands:
  - `import-source-pack`, `ingest`, `cluster`, `seed-topics`, `tag-topics`, `recompute-trending`, `pipeline`
- Implemented Stage 2 clustering worker in `curious_now/clustering.py` (config-driven; writes clusters, items, logs, search docs).
- Implemented Stage 2 topic tagging worker in `curious_now/topic_tagging.py` with a seed file under `config/`.

Config added:

- `config/clustering.v0.json`
- `config/topics.seed.v0.json`
- `config/source_pack.sample.v0.json`

Testing:

- Added integration test `tests/test_integration_end_to_end_pipeline.py` (ingest → cluster → tag → feed/search).
- Updated tests to flush Redis between tests to avoid cross-test cache contamination when `CN_REDIS_URL` is set.

Verification:

- `CN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curious_now CN_ADMIN_TOKEN=... CN_REDIS_URL=redis://localhost:6379/0 pytest -q` → `21 passed`
