# Deployment Guide

Deploy Curious Now to production: **FastAPI API** on Render, **Next.js frontend** on Vercel, **pipeline worker** on your local machine (using your local LLM), backed by managed Postgres.

---

## Architecture

```
┌─────────────────┐       ┌──────────────────────────┐
│  Vercel          │       │  Render                  │
│  (Next.js)       │──────▶│  Web Service (FastAPI)   │
│  web/            │  API  │  curious-now-api         │
└─────────────────┘       └──────────┬───────────────┘
                                     │
┌─────────────────┐                  │
│  Your Machine    │                  │
│  run_resilient   │                  │
│  _sync.py        │─────────────────┤
│  (local LLM)     │                  │
└─────────────────┘                  │
                                     ▼
                            ┌──────────────┐
                            │  Neon         │
                            │  (Postgres +  │
                            │   pgvector)   │
                            └──────────────┘
```

The API and your local pipeline worker share the same Neon database. The frontend is a Next.js app on Vercel that calls the API. Redis is optional and not needed for this setup.

---

## Step 1. Create Accounts

You need three services:

| Service | Plan | Cost | Purpose |
|---------|------|------|---------|
| [Neon](https://neon.tech) | **Launch** | ~$19/mo | Postgres + pgvector (always-on, no suspend) |
| [Render](https://render.com) | **Starter** | $7/mo | API server (always-on, no cold starts) |
| [Vercel](https://vercel.com) | Free | $0 | Next.js frontend |

**Total: ~$26/month.**

Do not use free tiers for the database or API — Neon free suspends after 5 minutes of inactivity and Render free sleeps after 15 minutes. Both will cause downtime.

Locally you need:
- Python 3.13+ with this repo's dependencies installed (`pip install -e .` or `uv sync`)
- A working LLM setup (Claude CLI, Codex CLI, or Ollama)

---

## Step 2. Set Up Database (Neon)

1. Create a new Neon project. Pick a region close to Render's Oregon (us-west) or Frankfurt (eu) region.
2. Choose the **Launch** plan during creation.
3. In the Neon SQL editor, enable pgvector:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

4. Copy the connection string:

   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
   ```

   Save this — you'll use it as `CN_DATABASE_URL` everywhere.

---

## Step 3. Deploy the API (Render)

### 3a. Deploy via Blueprint

1. In Render, go to **Blueprints** > **New Blueprint Instance**.
2. Connect your GitHub repo.
3. Render reads `render.yaml` and creates the `curious-now-api` web service.
4. **Change the plan from Free to Starter** in the service settings ($7/mo).
5. Set the environment variables below, then click **Apply**.

### 3b. Environment Variables

Set these in the Render dashboard for the `curious-now-api` service:

| Variable | Value | Notes |
|----------|-------|-------|
| `CN_DATABASE_URL` | Your Neon connection string | Required |
| `CN_ADMIN_TOKEN` | A random secret (e.g. `openssl rand -hex 32`) | Required — protects admin endpoints |
| `CN_PUBLIC_APP_BASE_URL` | `https://your-app.onrender.com` | Update later when you add a custom domain |
| `CN_CORS_ALLOWED_ORIGINS` | `https://your-app.vercel.app` | Your Vercel frontend URL (update after step 6) |
| `CN_LLM_ADAPTER` | `mock` | The API doesn't run the pipeline — `mock` is fine here |

Leave `CN_REDIS_URL` empty — Redis is optional and not needed for this setup.

The remaining variables are set automatically by `render.yaml` with production defaults (connection pooling, security headers, proxy trust, 30s statement timeout).

### 3c. Verify

Migrations run automatically before each deploy. After the deploy completes:

```bash
curl https://your-app.onrender.com/livez
# {"status":"ok"}

curl https://your-app.onrender.com/readyz
# {"status":"ready"}
```

If `/readyz` returns 503, check that `CN_DATABASE_URL` is correct and that your Neon project is active.

---

## Step 4. Seed the Database

Before running the pipeline, seed sources and topics. Run these locally, pointing at your Neon database:

```bash
export CN_DATABASE_URL="postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require"

python -m curious_now.cli import-source-pack config/source_pack.sample.v0.json
python -m curious_now.cli seed-topics-v1 --path config/topics.seed.v1.json
```

Both commands are idempotent — safe to run multiple times. You should see log output confirming sources and topics were imported.

---

## Step 5. Run the Pipeline Locally

This is the core of your setup. The pipeline ingests feeds, hydrates full text, clusters items, generates AI content, and computes trending scores — all using your local LLM.

### 5a. Create a `.env` file

Create a `.env` file in the repo root (it's already in `.gitignore`):

```bash
CN_DATABASE_URL=postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
CN_LLM_ADAPTER=claude-cli
```

Set `CN_LLM_ADAPTER` to whichever LLM you have locally: `claude-cli`, `codex-cli`, or `ollama`.

### 5b. First run (single cycle)

Run one full cycle to verify everything works end-to-end:

```bash
python scripts/run_resilient_sync.py \
  --throughput-profile low \
  --run-migrations \
  --stop-on-error
```

This runs: ingest > hydrate papers > hydrate articles > cluster > tag > takeaways > deep dives > enrich > promote > trending — then exits.

Watch the output. You should see each step complete with `ok`. If a step fails, `--stop-on-error` halts immediately so you can fix it.

### 5c. Continuous loop

Once the first run succeeds, start the continuous loop:

```bash
python scripts/run_resilient_sync.py \
  --loop \
  --throughput-profile low
```

This repeats the full pipeline every 10 minutes (the `low` profile interval). Leave it running in a terminal or tmux/screen session.

### 5d. Throughput profiles

| Profile | Cycle interval | Feeds/cycle | Items/feed | Clusters | Takeaways | Deep dives |
|---------|---------------|-------------|------------|----------|-----------|------------|
| `low` | 10 min | 10 | 100 | 400 | 60 | 20 |
| `balanced` | 5 min | 25 | 200 | 1,200 | 120 | 40 |
| `high` | 3 min | 50 | 250 | 2,500 | 250 | 80 |

Start with `low`. Once you're comfortable with the LLM costs and cycle times, switch to `balanced`. Use `high` only for bulk catch-up ingestion.

### 5e. Notes

- The pipeline acquires a PostgreSQL advisory lock, so only one instance runs at a time. Safe to restart without coordination.
- Press Ctrl-C to stop gracefully. The current step finishes, then the process exits.
- Use `--allow-mock-llm` to test ingestion and clustering without a real LLM (AI-generated content steps are skipped).
- Use `--log-level DEBUG` for verbose output when troubleshooting.

---

## Step 6. Deploy the Frontend (Vercel)

### 6a. Import project

1. In Vercel, click **Add New Project** > **Import Git Repository**.
2. Select your repo.
3. Set **Root Directory** to `web/`.
4. Confirm build settings (Vercel auto-detects Next.js):
   - **Build Command:** `npm run build`
   - **Output Directory:** `.next`
   - **Install Command:** `npm install`

### 6b. Environment variables

Set these in the Vercel project settings:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://your-app.onrender.com/v1` (include `/v1`) |
| `NEXT_PUBLIC_APP_URL` | `https://your-app.vercel.app` |
| `NEXT_PUBLIC_ENABLE_FOR_YOU` | `false` |
| `NEXT_PUBLIC_ENABLE_ENTITIES` | `false` |
| `NEXT_PUBLIC_ENABLE_LINEAGE` | `true` |
| `NEXT_PUBLIC_PWA_ENABLED` | `true` |

### 6c. Deploy

Click **Deploy**. After it finishes, visit your `.vercel.app` URL to verify the app loads.

---

## Step 7. Custom Domains

### API (Render)

1. In the Render service settings, add your domain (e.g. `api.yourdomain.com`).
2. Add the DNS records Render provides at your registrar.
3. Wait for TLS certificate issuance.
4. Update `CN_PUBLIC_APP_BASE_URL` to `https://api.yourdomain.com` in Render env vars.
5. Update `CN_CORS_ALLOWED_ORIGINS` to include your frontend domain.

### Frontend (Vercel)

1. In Vercel project settings > Domains, add your domain (e.g. `yourdomain.com`).
2. Add the DNS records Vercel provides.
3. Update `NEXT_PUBLIC_API_URL` to `https://api.yourdomain.com/v1`.
4. Update `NEXT_PUBLIC_APP_URL` to `https://yourdomain.com`.
5. Redeploy (Vercel > Deployments > Redeploy, or push a commit).

---

## Step 8. Verify Everything

After completing steps 1-7, check each item:

- [ ] **API is live:** `curl https://api.yourdomain.com/livez` returns `{"status":"ok"}`
- [ ] **API is ready:** `curl https://api.yourdomain.com/readyz` returns `{"status":"ready"}`
- [ ] **Frontend loads:** Visit `https://yourdomain.com`, confirm the app renders
- [ ] **CORS working:** No CORS errors in browser dev console
- [ ] **Pipeline ran:** Your local terminal shows completed ingest/cluster/tag cycles
- [ ] **Frontend shows data:** The feed page displays clusters from the API
- [ ] **Admin works:** `curl -H "Authorization: Bearer $CN_ADMIN_TOKEN" https://api.yourdomain.com/v1/admin/stats` returns data

If the frontend shows no data, the most likely cause is that the pipeline hasn't completed a full cycle yet. Clusters start in `pending` status and become visible after the promote step.

---

## Step 9. Ongoing Operations

### Auto-deploy

Both Render and Vercel auto-deploy on push to your configured branch. Migrations run automatically on each Render deploy via the pre-deploy command.

### Upgrading the pipeline

When you're ready to run the pipeline unattended (instead of on your laptop), move it to a Render Background Worker. Add to `render.yaml`:

```yaml
  - type: worker
    name: curious-now-worker
    runtime: docker
    plan: starter
    dockerfilePath: ./Dockerfile
    dockerContext: .
    envVars:
      - key: CN_DATABASE_URL
        sync: false
      - key: CN_LLM_ADAPTER
        sync: false
      - key: CN_LLM_MODEL
        sync: false
    startCommand: >-
      python scripts/run_resilient_sync.py
      --loop
      --throughput-profile balanced
      --run-migrations
```

Set the same `CN_DATABASE_URL` and `CN_LLM_ADAPTER` env vars. The advisory lock ensures your local pipeline and the Render worker never run simultaneously — you can transition without downtime.

### Rollback

Use Render's deploy history or Vercel's deployment list to roll back to a previous version.

---

## Appendix A. CORS

The backend automatically allows these origins:

- `http://localhost:3000`, `http://localhost:3001` (local dev)
- The value of `CN_PUBLIC_APP_BASE_URL`

To add more origins (e.g. your Vercel `.vercel.app` URL and your custom domain), set `CN_CORS_ALLOWED_ORIGINS` as a comma-separated list:

```
CN_CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://your-app.vercel.app
```

All origins are merged and deduplicated.

---

## Appendix B. Environment Variables Reference

### Backend (`CN_*`)

All backend env vars are prefixed with `CN_` and configured in `curious_now/settings.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `CN_DATABASE_URL` | *(required)* | Postgres connection string |
| `CN_REDIS_URL` | `None` | Redis connection string (optional) |
| `CN_ADMIN_TOKEN` | `None` | Secret for admin endpoints |
| `CN_PUBLIC_APP_BASE_URL` | `http://localhost:8000` | Public API URL (used for CORS + links) |
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
| `CN_DEFAULT_QUIET_HOURS_START` | `22:00` | Default quiet hours start |
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

## Appendix C. Troubleshooting

### CORS Errors

- Verify `CN_CORS_ALLOWED_ORIGINS` includes your frontend domain (exact match, including `https://`).
- Check that `CN_PUBLIC_APP_BASE_URL` is set to the backend's URL.

### Database Connection Failures

- Confirm `CN_DATABASE_URL` ends with `?sslmode=require` for Neon.
- Check that pgvector is enabled: `CREATE EXTENSION IF NOT EXISTS vector;`
- Verify the Neon project is on the Launch plan (free tier suspends after inactivity).

### Migration Failures

- Check the pre-deploy command logs in the Render dashboard.
- Migrations are in `design_docs/migrations/` and run in filename order.
- Run migrations manually: `python -m curious_now.cli migrate`

### Pipeline Errors

- Check that `CN_LLM_ADAPTER` matches your local setup and the LLM is running.
- Use `--allow-mock-llm` to skip LLM-dependent steps and test ingestion/clustering only.
- Ensure source packs and topics have been seeded (step 4).
- Use `--log-level DEBUG` for detailed output.

### Frontend Shows No Data

- Confirm `NEXT_PUBLIC_API_URL` ends with `/v1`.
- Verify the backend is healthy (`/readyz` returns 200).
- Check that the pipeline has completed at least one full cycle (all steps through promote).
- Clusters start in `pending` status and become visible after the promote step runs.
