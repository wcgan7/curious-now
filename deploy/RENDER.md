# Full-Stack Deployment Guide (Render + Vercel)

Deploy the complete Curious Now stack: **FastAPI backend** on Render, **Next.js frontend** on Vercel, and a **pipeline worker** on Render — backed by external Postgres and Redis.

---

## Architecture Overview

```
┌─────────────────┐       ┌──────────────────────────┐
│  Vercel          │       │  Render                  │
│  (Next.js)       │──────▶│  Web Service (FastAPI)   │
│  web/            │  API  │  curious-now-api         │
└─────────────────┘       ├──────────────────────────┤
                          │  Background Worker       │
                          │  run_resilient_sync.py   │
                          └──────┬───────┬───────────┘
                                 │       │
                    ┌────────────┘       └────────────┐
                    ▼                                  ▼
           ┌──────────────┐                  ┌──────────────┐
           │  Neon         │                  │  Upstash      │
           │  (Postgres +  │                  │  (Redis)      │
           │   pgvector)   │                  └──────────────┘
           └──────────────┘
```

The backend API and pipeline worker share the same database and Redis instance. The frontend is a static Next.js app deployed to Vercel that calls the backend API.

---

## 1. Prerequisites

- This repo pushed to GitHub
- Accounts on:
  - [Render](https://render.com) — hosts the API and pipeline worker
  - [Vercel](https://vercel.com) — hosts the Next.js frontend
  - [Neon](https://neon.tech) — managed Postgres with pgvector
  - [Upstash](https://upstash.com) — managed Redis

---

## 2. Database Setup (Neon)

1. Create a new Neon project (any region — pick one close to your Render region).
2. In the Neon SQL editor, enable the pgvector extension:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

3. Copy the connection string. It will look like:

   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
   ```

   You'll use this as `CN_DATABASE_URL`.

---

## 3. Redis Setup (Upstash)

1. Create an Upstash Redis database (choose a region near your Render region).
2. Copy the connection string in `redis://` format:

   ```
   redis://default:password@xxx.upstash.io:6379
   ```

   You'll use this as `CN_REDIS_URL`.

---

## 4. Backend Deployment (Render)

### 4a. Deploy via Blueprint

1. In Render, go to **Blueprints** → **New Blueprint Instance**.
2. Connect your GitHub repo.
3. Render reads `render.yaml` and creates the `curious-now-api` web service.
4. Set the required environment variables when prompted (see below).
5. Click **Apply**.

### 4b. Required Environment Variables

Set these in the Render dashboard for the `curious-now-api` service:

| Variable | Required | Description |
|----------|----------|-------------|
| `CN_DATABASE_URL` | Yes | Neon Postgres connection string |
| `CN_REDIS_URL` | Yes | Upstash Redis connection string |
| `CN_ADMIN_TOKEN` | Yes | Secret token for admin API endpoints |
| `CN_PUBLIC_APP_BASE_URL` | Yes | Public URL of the API, e.g. `https://api.yourdomain.com` |
| `CN_LLM_ADAPTER` | Recommended | LLM backend: `claude-cli`, `codex-cli`, `ollama`, or `mock` (defaults to `ollama`) |
| `CN_LLM_MODEL` | No | Model name (adapter-specific; uses adapter default if unset) |

The following are set automatically by `render.yaml` with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `CN_COOKIE_SECURE` | `true` | Secure cookie flag (keep `true` in production) |
| `CN_TRUST_PROXY_HEADERS` | `true` | Trust `X-Forwarded-*` headers from Render's proxy |
| `CN_SECURITY_HEADERS_ENABLED` | `true` | Add security response headers |
| `CN_DB_POOL_ENABLED` | `true` | Enable connection pooling |
| `CN_DB_POOL_MIN_SIZE` | `1` | Minimum pool connections |
| `CN_DB_POOL_MAX_SIZE` | `10` | Maximum pool connections |
| `CN_DB_POOL_TIMEOUT_SECONDS` | `10` | Pool connection timeout |
| `CN_STATEMENT_TIMEOUT_MS` | `30000` | SQL statement timeout (30s) |

### 4c. Migrations

Migrations run automatically before each deploy via the pre-deploy command:

```
python -m curious_now.cli migrate
```

This applies any pending SQL migrations from `design_docs/migrations/`.

### 4d. Verify

After deploy completes:

```bash
curl https://your-render-url.onrender.com/livez
# → {"status":"ok"}

curl https://your-render-url.onrender.com/readyz
# → {"status":"ready"}
```

`/livez` always returns 200. `/readyz` returns 200 only when the database connection pool is ready (503 otherwise).

### 4e. Custom Domain

1. In the Render service settings, add your custom domain (e.g. `api.yourdomain.com`).
2. Add the DNS records Render provides at your domain registrar.
3. Wait for TLS certificate issuance.
4. Verify: `curl https://api.yourdomain.com/readyz`

---

## 5. Initial Data Seeding

After the backend is deployed and migrations have run, seed the database with sources and topics.

### Option A: Render Shell

Open a shell in the Render dashboard for the `curious-now-api` service:

```bash
python -m curious_now.cli import-source-pack config/source_pack.sample.v0.json
python -m curious_now.cli seed-topics-v1 --path config/topics.seed.v1.json
```

### Option B: Local CLI with Remote DB

Set `CN_DATABASE_URL` to your Neon connection string locally, then run:

```bash
CN_DATABASE_URL="postgresql://..." python -m curious_now.cli import-source-pack config/source_pack.sample.v0.json
CN_DATABASE_URL="postgresql://..." python -m curious_now.cli seed-topics-v1 --path config/topics.seed.v1.json
```

Both commands are idempotent — safe to run multiple times.

---

## 6. Frontend Deployment (Vercel)

### 6a. Import Project

1. In Vercel, click **Add New Project** → **Import Git Repository**.
2. Select your repo.
3. Set **Root Directory** to `web/`.
4. Vercel auto-detects Next.js. Confirm build settings:
   - **Build Command:** `npm run build`
   - **Output Directory:** `.next`
   - **Install Command:** `npm install`

### 6b. Environment Variables

Set these in the Vercel project settings:

| Variable | Example | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com/v1` | Backend API base URL (include `/v1`) |
| `NEXT_PUBLIC_APP_URL` | `https://yourdomain.com` | Frontend public URL |
| `NEXT_PUBLIC_ENABLE_FOR_YOU` | `false` | Enable "For You" personalized feed |
| `NEXT_PUBLIC_ENABLE_ENTITIES` | `false` | Enable entity pages |
| `NEXT_PUBLIC_ENABLE_LINEAGE` | `true` | Enable paper lineage view |
| `NEXT_PUBLIC_PWA_ENABLED` | `true` | Enable PWA support |

### 6c. Deploy

Click **Deploy**. Vercel builds the Next.js app and deploys it to a `.vercel.app` URL. You can add a custom domain in Vercel's domain settings.

---

## 7. Pipeline Worker Setup

The pipeline worker runs `scripts/run_resilient_sync.py`, which continuously ingests feeds, clusters items, generates AI takeaways and deep dives, and updates trending scores.

### Option A: Render Background Worker (Recommended)

Add a second service to your `render.yaml`:

```yaml
  - type: worker
    name: curious-now-worker
    runtime: docker
    plan: starter  # or free (sleeps when idle)
    dockerfilePath: ./Dockerfile
    dockerContext: .
    envVars:
      - key: CN_DATABASE_URL
        sync: false
      - key: CN_REDIS_URL
        sync: false
      - key: CN_LLM_ADAPTER
        sync: false
      - key: CN_LLM_MODEL
        sync: false
      - key: CN_ADMIN_TOKEN
        sync: false
      - key: CN_PUBLIC_APP_BASE_URL
        sync: false
    startCommand: >-
      python scripts/run_resilient_sync.py
      --loop
      --throughput-profile balanced
      --run-migrations
```

Then update the Blueprint in Render. Set the same `CN_DATABASE_URL`, `CN_REDIS_URL`, and LLM env vars.

### Option B: Render Cron Job

For lower-frequency pipeline runs, use a cron job instead:

```yaml
  - type: cron
    name: curious-now-pipeline
    runtime: docker
    plan: starter
    schedule: "*/10 * * * *"  # every 10 minutes
    dockerfilePath: ./Dockerfile
    dockerContext: .
    envVars:
      # ... same as above
    startCommand: >-
      python scripts/run_resilient_sync.py
      --throughput-profile balanced
      --run-migrations
```

Without `--loop`, the script runs once and exits.

### Throughput Profiles

| Profile | Interval | Feeds | Items/Feed | Clusters | Takeaways | Deep Dives |
|---------|----------|-------|------------|----------|-----------|------------|
| `low` | 10 min | 10 | 100 | 400 | 60 | 20 |
| `balanced` | 5 min | 25 | 200 | 1,200 | 120 | 40 |
| `high` | 3 min | 50 | 250 | 2,500 | 250 | 80 |

Use `low` for early launch or limited LLM budgets. Use `balanced` (default) for normal operation. Use `high` for large-scale ingestion.

### LLM Configuration

The pipeline uses an LLM for tagging, takeaways, and deep dives. Set `CN_LLM_ADAPTER` to one of:

- `claude-cli` — Uses the Claude CLI (requires Claude credentials on the worker)
- `codex-cli` — Uses the Codex CLI
- `ollama` — Local Ollama instance (not suitable for cloud workers)
- `mock` — Returns placeholder content (for testing only)

`CN_LLM_MODEL` optionally overrides the adapter's default model.

---

## 8. CORS & Networking

The backend automatically allows these origins:

- `http://localhost:3000`, `http://localhost:3001` (local dev)
- `https://curious.now`, `https://www.curious.now`, `https://staging.curious.now`
- The value of `CN_PUBLIC_APP_BASE_URL`

To add your Vercel frontend domain, set `CN_CORS_ALLOWED_ORIGINS` on the backend:

```
CN_CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://your-app.vercel.app
```

This is a comma-separated list. All origins are merged and deduplicated.

`CN_PUBLIC_APP_BASE_URL` is also used to generate links in notifications and emails, so set it to the backend's public URL.

---

## 9. Environment Variables Reference

### Backend (`CN_*`)

All backend env vars are prefixed with `CN_` and configured in `curious_now/settings.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `CN_DATABASE_URL` | *(required)* | Postgres connection string |
| `CN_REDIS_URL` | `None` | Redis connection string |
| `CN_ADMIN_TOKEN` | `None` | Secret for admin endpoints |
| `CN_PUBLIC_APP_BASE_URL` | `http://localhost:8000` | Public API URL (used for CORS + notification links) |
| `CN_CORS_ALLOWED_ORIGINS` | `None` | Comma-separated extra CORS origins |
| `CN_COOKIE_SECURE` | `false` | Set `true` in production |
| `CN_LOG_MAGIC_LINK_TOKENS` | `false` | Log magic link tokens (dev only) |
| `CN_TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-*` headers |
| `CN_SECURITY_HEADERS_ENABLED` | `true` | Add security response headers |
| `CN_DB_POOL_ENABLED` | `true` | Enable DB connection pooling |
| `CN_DB_POOL_MIN_SIZE` | `1` | Min pool connections |
| `CN_DB_POOL_MAX_SIZE` | `10` | Max pool connections |
| `CN_DB_POOL_TIMEOUT_SECONDS` | `10.0` | Pool connection wait timeout |
| `CN_PIPELINE_POOL_MAX_SIZE` | `20` | Max pool connections for pipeline |
| `CN_STATEMENT_TIMEOUT_MS` | `30000` | SQL statement timeout (ms) |
| `CN_LLM_ADAPTER` | `ollama` | LLM backend (`claude-cli`, `codex-cli`, `ollama`, `mock`) |
| `CN_LLM_MODEL` | `None` | LLM model override |
| `CN_LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `CN_LOG_LEVEL` | `INFO` | Log level |
| `CN_SENDGRID_API_KEY` | `None` | SendGrid API key (for email notifications) |
| `CN_SMTP_HOST` | `None` | SMTP host (alternative to SendGrid) |
| `CN_SMTP_PORT` | `587` | SMTP port |
| `CN_SMTP_USERNAME` | `None` | SMTP username |
| `CN_SMTP_PASSWORD` | `None` | SMTP password |
| `CN_SMTP_USE_TLS` | `true` | SMTP TLS |
| `CN_EMAIL_FROM_ADDRESS` | `hello@curious.now` | Sender email address |
| `CN_EMAIL_FROM_NAME` | `Curious Now` | Sender display name |
| `CN_UNPAYWALL_EMAIL` | `None` | Email for Unpaywall API (paper hydration) |
| `CN_DEFAULT_TIMEZONE` | `UTC` | Default timezone for notification scheduling |
| `CN_DEFAULT_QUIET_HOURS_START` | `22:00` | Default quiet hours start (notifications paused) |
| `CN_DEFAULT_QUIET_HOURS_END` | `08:00` | Default quiet hours end |

### Frontend (`NEXT_PUBLIC_*`)

Set in the Vercel dashboard or in `web/.env.local`.

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/v1` | Backend API base URL (include `/v1`) |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | Frontend public URL |
| `NEXT_PUBLIC_ENABLE_FOR_YOU` | `false` | Enable personalized feed |
| `NEXT_PUBLIC_ENABLE_ENTITIES` | `false` | Enable entity pages |
| `NEXT_PUBLIC_ENABLE_LINEAGE` | `true` | Enable paper lineage view |
| `NEXT_PUBLIC_PWA_ENABLED` | `true` | Enable PWA support |

---

## 10. Post-Deploy Verification Checklist

- [ ] **Backend health:** `GET /livez` → `{"status":"ok"}`
- [ ] **Backend readiness:** `GET /readyz` → `{"status":"ready"}`
- [ ] **Frontend loads:** Visit your Vercel URL, confirm the app renders
- [ ] **Frontend fetches data:** The feed page loads clusters from the API
- [ ] **CORS working:** No CORS errors in browser console
- [ ] **Pipeline running:** Check worker logs in Render dashboard — you should see ingest/cluster/tag cycles
- [ ] **Admin endpoints:** `curl -H "Authorization: Bearer $CN_ADMIN_TOKEN" https://api.yourdomain.com/v1/admin/stats` returns data

---

## 11. Upgrading & Maintenance

- **Auto-deploy:** Both Render and Vercel auto-deploy on push to your configured branch (configurable in each dashboard).
- **Migrations:** Run automatically on each Render deploy via the pre-deploy command. No manual steps needed.
- **Pipeline worker:** Restarts automatically after deploy. Uses PostgreSQL advisory locks to prevent duplicate runs.
- **Rollback:** Use Render's deploy history or Vercel's deployment list to roll back to a previous version.

---

## 12. Troubleshooting

### CORS Errors

- Verify `CN_CORS_ALLOWED_ORIGINS` includes your frontend domain.
- Check that `CN_PUBLIC_APP_BASE_URL` is set to the backend's URL.
- Both values are added to the allowed origins list automatically.

### Database Connection Failures

- Confirm `CN_DATABASE_URL` uses `?sslmode=require` for Neon.
- Check that pgvector is enabled: `CREATE EXTENSION IF NOT EXISTS vector;`
- Verify the Neon project is not suspended (free tier suspends after inactivity).

### Migration Failures

- Check the pre-deploy command logs in Render.
- Migrations are in `design_docs/migrations/` and run in alphabetical order.
- You can run migrations manually: `python -m curious_now.cli migrate`

### Pipeline Not Running

- Check the worker service logs in Render for errors.
- Verify `CN_LLM_ADAPTER` is set to a valid adapter with proper credentials.
- Use `--allow-mock-llm` for testing without a real LLM.
- Ensure source packs and topics have been seeded (section 5).

### Frontend Shows No Data

- Confirm `NEXT_PUBLIC_API_URL` ends with `/v1`.
- Verify the backend is healthy (`/readyz`).
- Check that the pipeline has run at least one full cycle (ingest → cluster → promote).
- Clusters start in `pending` status and are promoted to `active` automatically.

### Free Tier Limitations

- Render free web services sleep after 15 minutes of inactivity and cold-start on the next request.
- Neon free tier suspends after 5 minutes of inactivity.
- For always-on service, upgrade to Render's Starter plan ($7/mo) and Neon's Launch plan.
