# Production Readiness Review - v1 (No Auth)

**Date:** 2026-02-07
**Branch:** main (user features removed)
**Overall Score:** 50% - Not Production Ready

---

## Critical Blockers (Must Fix Before Launch)

| Issue | Severity | Effort | File/Location |
|-------|----------|--------|---------------|
| No continuous content pipeline | CRITICAL | 4-6h | `curious_now/cli.py` |
| No connection pooling | CRITICAL | 4-6h | `curious_now/db.py` |
| No Dockerfile | CRITICAL | 2-4h | Create `Dockerfile` |
| No CI/CD (GitHub Actions) | CRITICAL | 4-6h | Create `.github/workflows/` |
| No global exception handler | CRITICAL | 2-3h | `curious_now/api/app.py` |
| No security headers | CRITICAL | 2-3h | Add middleware in `app.py` |
| No `/metrics` endpoint exposed | CRITICAL | 1h | `curious_now/api/app.py` |

---

## What's Already Good

| Area | Status | Location |
|------|--------|----------|
| Structured JSON logging | Excellent | `curious_now/logging_config.py` |
| Rate limiting | Implemented | `curious_now/rate_limit.py` |
| CORS configuration | Good | `curious_now/api/app.py` |
| Migration system | Solid | `curious_now/migrations.py` |
| PWA/offline support | Good | `web/next.config.js` |
| Metrics collection | Implemented (not exposed) | `curious_now/metrics.py` |
| Feature flags (frontend) | Working | `web/lib/config/env.ts` |
| Pydantic settings | Good | `curious_now/settings.py` |

---

## Deployment Options (Cheapest Path)

### Architecture Requirements

| Component | Technology | Notes |
|-----------|------------|-------|
| Frontend | Next.js 16 | PWA, static + SSR |
| Backend | FastAPI | Python 3.13+ |
| Database | PostgreSQL + pgvector | Vector embeddings for semantic search |
| Cache | Redis | Rate limiting, caching |
| LLM | Claude API | Deep dives, intuition generation |

### Option 1: Free Tier Stack ($0/month)

| Component | Service | Limitation |
|-----------|---------|------------|
| Frontend | Vercel | Free for Next.js |
| Backend | Render or Fly.io free tier | Spins down after 15 min idle → 10-30s cold starts |
| PostgreSQL | Supabase or Neon | 500MB free, both support pgvector |
| Redis | Upstash | 10k commands/day free |

**Trade-off**: Cold starts on backend after idle periods. Fine for low-traffic/personal use.

### Option 2: Always-On VPS ($5/month) ← Recommended

| Component | Service | Cost |
|-----------|---------|------|
| Frontend | Vercel | $0 |
| Backend + Postgres + Redis | Hetzner CX22 (2 vCPU, 4GB RAM) | €4.85/month |
| Background jobs | Cron on same VPS | $0 |

Run everything with Docker Compose on a single VPS:
```bash
# /etc/cron.d/curious-now
*/15 * * * * cd /app && curious-now ingest && curious-now cluster && curious-now tag-topics
0 */4 * * *  cd /app && curious-now generate-deep-dives --limit 50
15 */4 * * * cd /app && curious-now generate-intuition --limit 50
```

**Benefits**:
- No cold starts
- Background jobs run locally
- Single place to manage everything
- Cron is simple and reliable

### Option 3: Minimal PaaS (~$7-10/month)

| Component | Service | Cost |
|-----------|---------|------|
| Frontend | Vercel | $0 |
| Backend | Railway or Render paid tier | ~$5-7/month |
| PostgreSQL | Supabase/Neon free tier | $0 |
| Redis | Upstash free tier | $0 |

### Ongoing Costs (All Options)

- **Claude API**: Variable based on deep dive / intuition generation volume
- **Domain**: ~$10-15/year (optional, can use free subdomain)

### Chosen Strategy: Option 2 + Local Ingestion

**Hosting (VPS):**
- Frontend: Vercel (free)
- Backend API + Postgres + Redis: Hetzner VPS (~$5/month)
- Serves the web app and API only

**Content Pipeline (Local):**
- Run ingestion, clustering, tagging, and LLM generation locally
- Push directly to the production database
- Trigger manually or via local cron/scheduler

```
┌─────────────────────────────────────────────────────────────┐
│  LOCAL MACHINE                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  curious-now pipeline --source-pack config/sources  │   │
│  │  curious-now generate-deep-dives                    │   │
│  │  curious-now generate-intuition                     │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│                         │ writes to                         │
│                         ▼                                   │
│              ┌─────────────────────┐                       │
│              │  Prod DB (remote)   │◄────────────┐         │
│              │  Hetzner VPS        │             │         │
│              └─────────────────────┘             │         │
└─────────────────────────────────────────────────────────────┘
                                                   │
                          ┌────────────────────────┘
                          │ reads from
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  HETZNER VPS ($5/month)                                     │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │
│  │  FastAPI      │  │  PostgreSQL   │  │  Redis        │   │
│  │  (API only)   │  │  + pgvector   │  │  (cache)      │   │
│  └───────────────┘  └───────────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ serves
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  VERCEL (free)                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Next.js Frontend (SSR + Static)                      │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Benefits of this approach:**
- LLM calls (Claude API) run on your local machine - no VPS timeout issues
- Full control over when ingestion happens
- VPS only needs to serve API requests - minimal resources needed
- Can watch logs in real-time during ingestion
- No need to SSH into VPS for debugging pipeline issues

**Local workflow:**
```bash
# Set prod database URL
export CN_DATABASE_URL=postgresql://user:pass@vps-ip:5432/curious_now

# Run full pipeline
curious-now pipeline --source-pack config/sources.json --seed-topics

# Generate LLM content
curious-now generate-deep-dives --limit 50
curious-now generate-intuition --limit 50
```

**Required for this setup:**
- [ ] Expose Postgres port on VPS (with firewall rules for your IP only)
- [ ] Or use SSH tunnel: `ssh -L 5432:localhost:5432 user@vps`
- [ ] Separate `.env.local` and `.env.prod` configurations

---

## Category Breakdown

### 1. Deployment (20%)

**Exists:**
- `docker-compose.yml` (dev only - Postgres + Redis)
- `Makefile` with dev targets
- `.env.example`

**Missing:**
- [ ] Production Dockerfile (multi-stage, non-root user)
- [ ] `docker-compose.prod.yml`
- [ ] `.dockerignore`
- [ ] Cron job configuration for background tasks

**Note:** See "Deployment Options" section above for recommended hosting strategy. Kubernetes is overkill for v1 - use Docker Compose on a VPS instead.

### 2. CI/CD (0%)

**Missing:**
- [ ] `.github/workflows/test.yml` - Run pytest
- [ ] `.github/workflows/lint.yml` - Run ruff + mypy
- [ ] `.github/workflows/build.yml` - Build Docker image
- [ ] `.github/workflows/frontend.yml` - Run vitest + build
- [ ] Dependabot configuration
- [ ] Code coverage reporting

### 3. Backend (70%)

**Exists:**
- Basic HTTPException handling in routes
- Structured logging with JSON formatter
- `/healthz` endpoint
- Rate limiting with Redis
- CORS middleware

**Missing:**
- [ ] Global exception handler (`@app.exception_handler`)
- [ ] Request ID middleware (X-Request-ID)
- [ ] Readiness probe (`/readyz` - checks DB/Redis)
- [ ] Liveness probe (`/livez`)
- [ ] Security headers middleware:
  - X-Frame-Options: DENY
  - X-Content-Type-Options: nosniff
  - Strict-Transport-Security (HSTS)
  - Content-Security-Policy
  - Referrer-Policy

### 4. Database (60%)

**Exists:**
- Migration runner with tracking
- Proper indexes defined in migrations
- pgvector for semantic search

**Missing:**
- [ ] Connection pooling (psycopg pool or pgbouncer)
- [ ] Connection timeout configuration
- [ ] Statement timeout
- [ ] Slow query logging
- [ ] Rollback mechanism for migrations

**Current Issue:** `curious_now/db.py` creates new connection per request - will exhaust connections under load.

### 5. Frontend (75%)

**Exists:**
- Next.js 16 with optimizations
- PWA with next-pwa
- Global error.tsx
- TypeScript strict mode
- React Query for async state

**Missing:**
- [ ] Sentry error tracking
- [ ] Skeleton loading screens
- [ ] Bundle size analysis
- [ ] Per-route error boundaries

### 6. Testing (50%)

**Exists:**
- 24 test files in `/tests/`
- pytest + pytest-asyncio
- vitest for frontend
- Playwright for E2E
- Integration tests for all stages

**Missing:**
- [ ] Coverage reporting (pytest-cov)
- [ ] Coverage enforcement in CI
- [ ] Unit tests for business logic
- [ ] Frontend component tests

### 7. Configuration (60%)

**Exists:**
- `.env.example` with all variables
- Pydantic Settings with CN_ prefix
- Feature flags in frontend

**Missing:**
- [ ] Startup validation for required env vars
- [ ] Secrets manager integration (AWS/GCP/Vault)
- [ ] Log redaction for sensitive data
- [ ] Backend feature flags

### 8. Monitoring (65%)

**Exists:**
- `curious_now/metrics.py` - Prometheus format metrics
- MetricsMiddleware for request tracking
- Business metrics (clusters, searches, etc.)

**Missing:**
- [ ] `/metrics` route to expose metrics
- [ ] Database connection pool metrics
- [ ] Redis cache hit/miss metrics
- [ ] Alerting rules
- [ ] Dashboard setup (Grafana)

### 9. Continuous Content Pipeline (0%)

**Current State:**
All processing is CLI-driven with no automation. Each stage must be invoked manually:
```bash
curious-now ingest              # Fetch RSS feeds
curious-now cluster             # Group related items
curious-now tag-topics          # Apply topic tags
curious-now generate-deep-dives # LLM: technical explainers
curious-now generate-intuition  # LLM: ELI5/ELI20 summaries
```

**The Problem:**
- No way to trigger LLM generation automatically after ingestion
- No scheduled/continuous feed polling
- Notifications module referenced in CLI but not implemented

**Exists:**
- CLI commands for all pipeline stages
- `curious-now pipeline` command (runs ingest → cluster → tag)

**Missing:**
- [ ] **Ingest-to-LLM trigger**: Run deep-dive + intuition immediately after new content ingested
- [ ] **Watch mode for local dev**: Single command that polls feeds and processes continuously
- [ ] **Production scheduler**: Cron/systemd timers or embedded scheduler (APScheduler)
- [ ] **Notifications module**: `curious_now/notifications.py` (imported but doesn't exist)

**Local Development Approach:**
For now, extend `pipeline` command or create new `watch` command:
```bash
# Desired: single command for local content refresh
curious-now watch --interval 15m --generate-llm
```

This would:
1. Poll feeds every 15 minutes
2. Cluster new items
3. Tag topics
4. Immediately trigger deep-dive + intuition generation for new clusters

**Production Approach:**
- Option A: Cron jobs on VPS (simplest, $0 extra)
- Option B: GitHub Actions scheduled workflows (free tier)
- Option C: Celery + Redis beat scheduler (if scaling needed)

---

## Implementation Plan (Prioritized)

### Phase 1: Local Content Pipeline (Do First)

**Goal:** Get content flowing locally before worrying about deployment.

- [ ] Run initial ingestion with new sources
  ```bash
  curious-now pipeline --source-pack config/sources.json --seed-topics --force
  ```
- [ ] Verify items ingested and clusters created
- [ ] Run LLM generation (deep dives + intuition)
  ```bash
  curious-now generate-deep-dives --limit 50
  curious-now generate-intuition --limit 50
  ```
- [ ] Verify frontend displays content correctly (`make dev` / `npm run dev`)
- [ ] Iterate: adjust sources, re-run pipeline as needed

**Outcome:** Working local setup with real content.

---

### Phase 2: Production Infrastructure (Est. 8-10h)

**Goal:** Minimum viable deployment artifacts.

#### 2a. Docker Setup (3-4h)
- [ ] Create `Dockerfile` (multi-stage, non-root user)
- [ ] Create `docker-compose.prod.yml` (API + Postgres + Redis)
- [ ] Create `.dockerignore`
- [ ] Test locally: `docker-compose -f docker-compose.prod.yml up`

#### 2b. Critical Code Fixes (4-5h)
- [ ] Add connection pooling to `curious_now/db.py`
  ```python
  from psycopg_pool import ConnectionPool
  pool = ConnectionPool(conninfo=settings.database_url, min_size=2, max_size=10)
  ```
- [ ] Add global exception handler in `app.py`
- [ ] Add `/readyz` endpoint (checks DB + Redis connectivity)

#### 2c. Environment Configuration (1h)
- [ ] Create `.env.prod.example` with production settings
- [ ] Document which vars are required vs optional

**Outcome:** Docker image that can be deployed anywhere.

---

### Phase 3: VPS Deployment (Est. 3-4h)

**Goal:** Live production environment.

#### 3a. Hetzner Setup
- [ ] Create Hetzner CX22 instance (~$5/month)
- [ ] Install Docker + Docker Compose
- [ ] Configure firewall (allow 80, 443, SSH; restrict 5432 to your IP)
- [ ] Set up SSH key access

#### 3b. Deploy
- [ ] Copy `docker-compose.prod.yml` and `.env.prod` to VPS
- [ ] Pull/build Docker image
- [ ] Start services: `docker-compose up -d`
- [ ] Run migrations: `docker-compose exec api curious-now migrate`
- [ ] Verify API responds: `curl https://your-vps-ip/healthz`

#### 3c. Local → Prod DB Connection
- [ ] Option A: SSH tunnel script
  ```bash
  # scripts/prod-tunnel.sh
  ssh -L 5432:localhost:5432 root@your-vps-ip
  ```
- [ ] Option B: Direct connection (firewall your IP)
- [ ] Create `.env.prod.local` for local CLI pointing to prod DB

**Outcome:** API running on VPS, accessible from internet.

---

### Phase 4: Frontend Deployment (Est. 1-2h)

**Goal:** Live frontend on Vercel.

- [ ] Connect GitHub repo to Vercel
- [ ] Set environment variables (API URL pointing to VPS)
- [ ] Deploy: `vercel --prod` or push to main
- [ ] Verify frontend loads and fetches from API
- [ ] (Optional) Configure custom domain

**Outcome:** Full stack live.

---

### Phase 5: Polish (Optional for v1)

Lower priority - do after everything works:

- [ ] CI/CD with GitHub Actions
- [ ] Security headers middleware
- [ ] Sentry error tracking
- [ ] `/metrics` endpoint + monitoring
- [ ] HTTPS via Let's Encrypt / Caddy

---

## Summary: Minimum Path to Production

| Phase | What | Effort | Blocker? |
|-------|------|--------|----------|
| 1 | Local pipeline with real content | 1-2h | **Do now** |
| 2 | Dockerfile + connection pooling | 8-10h | Yes |
| 3 | VPS deployment | 3-4h | Yes |
| 4 | Vercel frontend | 1-2h | Yes |
| 5 | Polish (CI/CD, monitoring, etc.) | 10-15h | No |

**Total to live:** ~15-20h of focused work.

---

## Original Implementation Plan (Reference)

### Week 1: Critical Path (Est. 25-30h)

#### Day 1: Continuous Pipeline (Local)
- [ ] Add `--generate-llm` flag to `pipeline` command
  - After ingest+cluster+tag, trigger deep-dive + intuition for new clusters
- [ ] Create `curious-now watch` command for local dev
  - Poll feeds at configurable interval
  - Run full pipeline including LLM generation
  - Graceful shutdown on Ctrl+C
- [ ] Implement missing `curious_now/notifications.py` module (stub or full)

#### Day 2-3: Database & Docker
- [ ] Add connection pooling to `db.py`
  ```python
  from psycopg_pool import ConnectionPool
  pool = ConnectionPool(conninfo=settings.database_url, min_size=5, max_size=20)
  ```
- [ ] Create `Dockerfile`
- [ ] Create `docker-compose.prod.yml`
- [ ] Add `.dockerignore`

#### Day 3-4: CI/CD
- [ ] Create `.github/workflows/ci.yml`
  - Lint (ruff)
  - Type check (mypy)
  - Test (pytest)
  - Build Docker image
- [ ] Add Dependabot config

#### Day 5: Error Handling & Observability
- [ ] Add global exception handler in `app.py`
- [ ] Add request ID middleware
- [ ] Expose `/metrics` endpoint
- [ ] Add `/readyz` and `/livez` endpoints

### Week 2: Security & Monitoring (Est. 15-20h)

- [ ] Security headers middleware
- [ ] HTTPS redirect (production)
- [ ] Sentry integration (frontend + backend)
- [ ] Prometheus scraping setup
- [ ] Basic Grafana dashboard

### Week 3: Polish (Est. 10-15h)

- [ ] Load testing with k6
- [ ] Deployment runbook
- [ ] Rollback procedure
- [ ] On-call alerting setup

---

## Quick Wins (< 1 hour each)

1. Expose `/metrics` endpoint
2. Add `.dockerignore`
3. Add startup env validation
4. Document required env vars in README

---

## Files to Create

```
curious_now/notifications.py   # Missing module (imported but doesn't exist)
.github/
  workflows/
    ci.yml
    dependabot.yml
Dockerfile
docker-compose.prod.yml
.dockerignore
cron/
  curious-now.cron             # Cron job config for background tasks
```

Note: Kubernetes manifests deferred - using Docker Compose on VPS for v1.

---

## Files to Modify

| File | Changes |
|------|---------|
| `curious_now/cli.py` | Add `watch` command, add `--generate-llm` to `pipeline` |
| `curious_now/db.py` | Add connection pooling |
| `curious_now/api/app.py` | Add exception handlers, security headers, /metrics route |
| `curious_now/settings.py` | Add startup validation |
| `pyproject.toml` | Add psycopg-pool, sentry-sdk |

---

## Reference Commands

```bash
# Run tests
make test

# Run linter
make lint

# Type check
make typecheck

# All checks
make check

# Start dev environment
make dev-up

# Run API
make api
```

---

## Estimated Total Effort

| Phase | Hours |
|-------|-------|
| Week 1 (Critical + Pipeline) | 25-30h |
| Week 2 (Security) | 15-20h |
| Week 3 (Polish) | 10-15h |
| **Total** | **50-65h** |

With focused effort, v1 can be production-ready in 2-3 weeks.
