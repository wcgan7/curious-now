# Curious Now (Backend)

Curious Now is a FastAPI backend for a “cluster-first” research/news product:

- It ingests items from sources (feeds), groups them into story clusters, and serves feeds/search.
- It is currently scoped for an authless launch (no user accounts/sessions/personalization endpoints exposed).
- It includes admin/governance tooling (feedback triage, topic/entity management, cluster merge/split, lineage).
- It ships with Postgres migrations and a reference OpenAPI spec in `design_docs/`.

This repo is intentionally “docs-first”: `design_docs/openapi.v0.yaml` and `design_docs/migrations/*.sql`
define the full target v0 contract. The current authless launch exposes a subset of that API.

For implementation history and verification notes, see `LOGBOOK.md`. For a tracked list of review issues,
see `CODE_REVIEW.md`.

## What’s Implemented (Stages 1–10)

High-level, v0 functionality implemented in this codebase:

- Stage 1: sources + item feed + admin source pack import
- Stage 2: cluster feed (latest/trending/for_you), topics, cluster detail, search (Postgres FTS + optional trigram)
- Stage 3: glossary lookup + glossary links on cluster detail
- Stage 4: cluster update log + topic lineage graph
- Stage 5–6: deferred for initial authless launch (no user accounts/sessions/personalization yet)
- Stage 7: best-effort Redis caching + weak ETags for some read endpoints
- Stage 8: feedback + governance/editorial admin ops (merge/split/quarantine, topic ops, lineage ops)
- Stage 9: rate limiting + identifier-first search for DOI/arXiv + retention tooling
- Stage 10: entities + experiments + feature flags (user entity follows deferred)

Pipeline note: `POST /v1/admin/ingestion/run` triggers a best-effort background ingestion run inside the API
process. Stage 2 clustering + topic tagging are implemented as CLI-driven worker jobs (run them from a
scheduler/cron in production).

## Tech Stack

- Python 3.13+
- FastAPI + Pydantic v2
- Postgres (tested with the docker image in `docker-compose.yml`, includes `pgvector`)
- Redis (optional; used for caching + rate limiting)
- psycopg (Postgres driver)

## Repo Layout

- `curious_now/api/` — FastAPI app + route modules per stage
- `curious_now/repo_stage*.py` — DB access functions (SQL)
- `curious_now/migrations.py` — migration runner (order follows `design_docs/ops_runbook.md`)
- `curious_now/cli.py` — CLI utilities (migrate, ingestion, clustering, notifications, retention)
- `design_docs/` — OpenAPI spec, stage docs, and the SQL migrations
- `config/` — worker configs + seed files (clustering, topics, sample source pack)
- `tests/` — unit tests + integration tests (Postgres required; Redis optional)

## Quick Start (Local Dev)

Prereqs:
- Python 3.13+
- Docker (for Postgres/Redis)

1. Create a virtualenv and install deps:
   - `make venv`
   - `make install`
2. Start Postgres + Redis:
   - `make dev-up`
3. Configure env (copy `.env.example` and export values in your shell):
   - `CN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curious_now`
   - `CN_REDIS_URL=redis://localhost:6379/0` (optional but recommended)
   - `CN_ADMIN_TOKEN=dev-admin-token` (required for `/v1/admin/*`)
4. Run migrations:
   - `make migrate`
5. Import a source pack (sample included):
   - `python -m curious_now.cli import-source-pack config/source_pack.sample.v0.json`
6. (Optional) Seed topics (v1 taxonomy, sample included):
   - `python -m curious_now.cli seed-topics-v1`
7. Run the API:
   - `make api`

Then:
- Liveness check: `curl http://localhost:8000/livez`
- Readiness check: `curl http://localhost:8000/readyz`
- Backward-compatible health check: `curl http://localhost:8000/healthz`
- OpenAPI UI: `http://localhost:8000/docs`

## Container Image (Backend)

Build:

- `docker build -t curious-now-api .`

Run:

- `docker run --rm -p 8000:8000 -e CN_DATABASE_URL=postgresql://... -e CN_REDIS_URL=redis://... -e CN_ADMIN_TOKEN=... curious-now-api`

## Hosted Deployment (Render First)

- Blueprint config: `render.yaml`
- Runbook: `deploy/RENDER.md`

This target is designed for a cheap first launch using one Render web service plus external Postgres/Redis.

## End-to-End Pipeline (Stage 1 → Stage 2)

The core data flow is:

1. **Ingest** RSS/Atom feeds into `items`
2. **Cluster** unassigned items into `story_clusters` + `cluster_items`
3. **Tag topics** (optional) by LLM classification into `cluster_topics`
4. **Recompute trending** metrics

Run it as a single command:

- `python -m curious_now.cli pipeline --force`

Or do it step-by-step:

- `python -m curious_now.cli ingest --force`
- `python -m curious_now.cli cluster`
- `python -m curious_now.cli tag-topics`
- `python -m curious_now.cli recompute-trending`

## Downtime-Tolerant Local Sync

For an ops-friendly local runner that can recover from temporary failures and keep the
remote DB updated, use:

- One pass: `make sync-once`
- Continuous loop: `make sync-loop`

Runner script: `scripts/run_resilient_sync.py`

Notes:
- Uses retries with exponential backoff for each step.
- Uses a Postgres advisory lock so overlapping resilient-sync processes skip instead of double-running.
- Defaults to `untagged` topic mode to reduce wasted retag LLM calls.
- Executes: ingest → hydrate-paper-text → cluster → tag → takeaways → deep-dives → trending.
- Includes throughput profiles:
  - `--throughput-profile low` for low daily volume / tighter LLM budget
  - `--throughput-profile balanced` (default) for typical early launch
  - `--throughput-profile high` for faster freshness at higher compute/LLM cost

## Configuration (Env Vars)

All settings use the `CN_` prefix.

Required:
- `CN_DATABASE_URL` — Postgres DSN

Optional:
- `CN_REDIS_URL` — enables Redis caching + rate limiting
- `CN_ADMIN_TOKEN` — required for admin routes (header `X-Admin-Token`)
- `CN_PUBLIC_APP_BASE_URL` — used when rendering notification links (default `http://localhost:8000`)

Security/ops toggles:
- `CN_COOKIE_SECURE` — set `true` in HTTPS deployments (default `false`)
- `CN_LOG_MAGIC_LINK_TOKENS` — only for local/dev; when `true` the magic-link token is printed to stdout
  (default `false`)
- `CN_TRUST_PROXY_HEADERS` — if `true`, rate limiting will prefer `X-Forwarded-For` / `X-Real-IP`
  (only enable behind a trusted proxy; default `false`)

Stage 6 defaults (used when a user has no notification settings stored):
- `CN_DEFAULT_TIMEZONE` (default `UTC`)
- `CN_DEFAULT_QUIET_HOURS_START` (default `22:00`)
- `CN_DEFAULT_QUIET_HOURS_END` (default `08:00`)

## Common Dev Commands

- `make test` — runs the test suite (unit tests always; integration tests are skipped without env)
- `make lint` — `ruff check .`
- `make typecheck` — `mypy curious_now`
- `make check` — test + lint + typecheck

## Integration Tests

Integration tests require a running Postgres (and some tests also require Redis).

Example:

- `CN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curious_now CN_ADMIN_TOKEN=test-admin-token pytest -q`
- `CN_DATABASE_URL=... CN_ADMIN_TOKEN=... CN_REDIS_URL=redis://localhost:6379/0 pytest -q`

## CLI

All CLI commands are invoked as `python -m curious_now.cli ...` (or via the `make` targets).

- Migrate DB: `python -m curious_now.cli migrate`
- Import source pack: `python -m curious_now.cli import-source-pack config/source_pack.sample.v0.json`
- Enqueue notification jobs: `python -m curious_now.cli enqueue-notifications`
- Send due notification jobs (dev sender): `python -m curious_now.cli send-notifications`
- Purge logs by retention policy (dry-run by default): `python -m curious_now.cli purge-logs`
- Ingest due feeds: `python -m curious_now.cli ingest --force`
- Cluster unassigned items: `python -m curious_now.cli cluster`
- Seed topics (v1): `python -m curious_now.cli seed-topics-v1`
- Tag topics for recent clusters: `python -m curious_now.cli tag-topics`
- Recompute trending: `python -m curious_now.cli recompute-trending`
- Run end-to-end pipeline: `python -m curious_now.cli pipeline --force`

## Admin Auth

Admin routes are protected by a static token in the `X-Admin-Token` header:

- Set `CN_ADMIN_TOKEN` in the environment.
- Send `X-Admin-Token: <token>` on requests to `/v1/admin/*`.

In v0 this is intentionally simple; for production you’d likely replace this with real admin identities and
audit controls.

## Design Docs

- API contract: `design_docs/openapi.v0.yaml`
- Migrations: `design_docs/migrations/`
- Operational notes: `design_docs/ops_runbook.md`
