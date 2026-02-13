# Render Deployment (Backend)

This repo includes `render.yaml` for a low-cost first launch of the backend API.

## What This Config Does

- Deploys `curious_now.api.app:app` via the repo `Dockerfile`
- Uses `/readyz` as health check
- Runs `python -m curious_now.cli migrate` before deploy
- Expects externally managed Postgres + Redis URLs via env vars

## Suggested Cheap-Start Stack

- Render web service (`plan: free`) for the API container
- External Postgres (for example Neon free tier)
- External Redis (for example Upstash free tier)

This avoids managed DB costs on day 1 while keeping your API on a hosted URL with custom domain support.

## Deploy Steps

1. Push this repo to GitHub.
2. In Render, create a Blueprint deploy from this repo (`render.yaml`).
3. Set required env vars:
   - `CN_DATABASE_URL`
   - `CN_REDIS_URL` (recommended)
   - `CN_ADMIN_TOKEN`
   - `CN_PUBLIC_APP_BASE_URL` (set to your API domain, e.g. `https://api.yourdomain.com`)
4. Deploy and verify:
   - `GET /livez` returns `200`
   - `GET /readyz` returns `200`

## Custom Domain

1. In Render service settings, add your custom domain (for example `api.yourdomain.com`).
2. Add the DNS records Render shows at your domain registrar.
3. Wait for TLS issuance and verify `https://api.yourdomain.com/readyz`.

## Important Limitation on Free Plan

Render free web services sleep when idle and may cold-start.

If you need always-on API and scheduled jobs, upgrade the web service plan and add scheduled workers/cron.
