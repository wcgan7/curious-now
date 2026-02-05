# Curious Now — Stage 1 PRD v0.1

**Stage 1 Blueprint (Self‑Contained)**

This is a single, complete PRD that combines:

* the **product PRD** (vision, UX, requirements, success metrics, policy),
* the **technical spec** (architecture, schemas, jobs, APIs, heuristics, observability), and
* the **Stage 1 execution plan** (milestones + ticket-style checklist + build order).

It’s written so you can move directly into Stage 1 implementation. Stage numbering across `design_docs/` follows `design_docs/implementation_plan_overview.md` (see also `design_docs/project_motivation.md` for the “why”).

---

## 1) Executive Summary

### 1.1 Vision

Build a science news app that:

1. **Aggregates responsibly** from multiple sources (RSS/APIs first),
2. **Organizes** coverage into canonical **StoryClusters** (deduped and multi-source),
3. **Explains** technical work in two layers (**Intuition → Deep Dive**) with citations,
4. Shows **trust + uncertainty** transparently (preprint vs peer-reviewed vs press release),
5. Tracks **updates and evolution** over time (what changed + lineage timelines).

### 1.2 One‑line value proposition

“Science news you can understand—then go deeper—with trust and updates built in.”

### 1.3 Product principles (non-negotiable)

1. **Source-first**: everything links back to primary sources; no invented facts.
2. **Progressive disclosure**: Intuition first, technical depth on demand.
3. **Transparency**: labels, uncertainty, and caveats are always visible.
4. **Anti-hype**: actively counter overstated claims and press-release spin.
5. **Canonical units**: the product unit is the **StoryCluster**, not individual links.

---

## 2) Definitions (Shared language)

* **Source**: A publisher/provider (NASA, Science.org, arXiv, MIT News, etc.).
* **Feed**: RSS/Atom/API endpoint for a Source.
* **Item**: One fetched piece of content from a Source (one article, one press release, one preprint link).
* **StoryCluster**: A canonical “story page” that groups multiple Items covering the same underlying event/paper.
* **Topic**: A taxonomy category users can browse/follow (Space, Biology, NLP, Climate…).
* **Glossary Entry**: A reusable “just‑in‑time” explanation for a term (transformer, p-value…).
* **Update Log**: A record of meaningful changes to a StoryCluster over time.
* **Lineage**: A graph/timeline that shows how ideas/models evolve (BERT → ALBERT, etc.).

---

## 3) Target Users & Jobs-to-be-Done

### 3.1 Personas

**P1 — Curious Generalist**
Wants: quick understanding, minimal jargon, clear “why it matters.”

**P2 — Student / Learner**
Wants: background knowledge while reading; glossary tooltips; topic browsing.

**P3 — Technical Reader**
Wants: method details, assumptions/limitations, paper links, multi-source context.

### 3.2 Primary jobs-to-be-done

* “Tell me the takeaway in 10 seconds.”
* “Explain it intuitively, then let me go deeper.”
* “Help me judge how trustworthy this is.”
* “Show what’s uncertain and what could change.”
* “Track updates and see how ideas evolved over time.”
* “Let me follow topics and get meaningful (not noisy) notifications.”

---

## 4) Scope, Staging, and Non‑Goals

### 4.1 Full vision feature set (for completeness)

**Organization & discovery**

* Multi-source ingestion (RSS/APIs first)
* Dedup + clustering into StoryClusters
* Feed tabs: Latest / Trending / For You
* Topic pages + taxonomy + related topics
* Search (clusters/topics; later semantic)

**Understanding layer**

* Takeaway (1 sentence)
* Intuition explanation (plain language)
* Deep Dive explanation (technical but readable)
* Assumptions + limitations
* Evidence panel grouped by source type
* Glossary tooltips (just-in-time learning)
* Method badges
* Anti-hype flags

**Trust & uncertainty**

* Trust box: source-type mix + diversity
* Confidence band (early / growing / established)
* “What could change this?” framing

**Time & evolution**

* Update tracking (“what changed since last time?”)
* Lineage timelines (BERT → ALBERT etc.)

**Personalization & retention**

* Accounts
* Follow topics, block sources, saves/bookmarks
* Reading mode default (Intuition-first vs Deep-first)
* Notifications + digests (topic updates & story updates)

**Platforms**

* Web first; mobile later; shared API for both.

### 4.2 Stage 1 scope (what we actually implement first)

Stage 1 builds the **foundation platform**:

* Ingest sources reliably
* Normalize and store Items (idempotent)
* Minimal API to serve a Latest feed
* Minimal web UI to browse + click out
* Admin + health visibility

### 4.3 Explicit non-goals (avoid scope creep)

* Republishing full paywalled content
* Acting as a peer-review authority or giving medical advice
* Deep personalization and ML-heavy ranking in Stage 1
* Advanced clustering/lineage in Stage 1 (that’s Stage 2+)

---

## 5) Content Policy & Labeling Requirements

### 5.1 Content type labels (must be present in the data model from Day 1)

Each Item must have a `content_type` label:

* `news` (journalism)
* `press_release` / institutional news
* `preprint`
* `peer_reviewed` / journal article
* `report` (government/NGO/standards)

### 5.2 Display rules (trust and safety)

* If `preprint`: always show “Not peer reviewed” disclaimer (Stage 3+ UI; label exists earlier).
* If paywalled: store minimal metadata + link out; do not store full article text unless explicitly allowed.
* Never present medical/scientific content as prescriptive advice; use uncertainty framing.

---

## 6) UX Requirements (Stage 1 and Future)

### 6.1 Stage 1 screens (must ship)

**A) Feed (Latest)**
Card shows:

* title
* source name
* published time
* badge (content type)
* snippet if present
* “Read original” link

**B) Sources Health (optional but recommended for ops)**
List sources and show:

* last fetched time
* error streak
* last error (if logged)

**C) Admin (must-have minimal)**

* add/edit/disable a feed
* view ingestion health
* optional: “run ingestion now”

### 6.2 Future screens (designed now, built later)

* StoryCluster page (Takeaway + Intuition + Deep Dive + trust box + update log)
* Topic pages (timeline + follow)
* Search (clusters/topics)
* Settings (reading level, follows/blocks, notifications)

---

## 7) Success Metrics (Stage 1 and Beyond)

### 7.1 Stage 1 operational success

* Ingestion success rate per feed
* New items/day by source
* Time from publication to appearing in feed
* Duplicate rate near zero (idempotency)

### 7.2 Product engagement (start measuring early, even before accounts)

* Feed CTR (click-through to original)
* Return visits per week (even anonymous)
* “Hide source” / “mute” later (Stage 5)

---

## 8) Technical Architecture (Stage 1 foundation)

### 8.1 Recommended v0 stack (assumption)

* **API**: Node/TypeScript (Fastify/Express)
* **Web**: Next.js (TypeScript)
* **Worker**: Node/TypeScript job runner
* **DB**: Postgres
* **Local dev**: Docker Compose
  (Any equivalent stack works if the interfaces are preserved.)

### 8.2 Services/modules

* **API Server**: serves feed and source health; later clusters/topics/search/user prefs
* **Ingestion Worker**: fetches feeds, parses, normalizes, upserts Items
* **Admin UI / Admin endpoints**: manage sources/feeds, health, manual trigger
* **(Later)** Processing worker for clustering/enrichment/updates/lineage
* **(Later)** Notifications worker for digests and alerts

### 8.3 Pipeline shape (future-proof)

Ingest → Normalize → (Stage 2: Cluster) → (Stage 3+: Enrich) → Rank → Serve → Learn

Stage 1 implements: **Ingest + Normalize + Serve**

---

## 9) Data Model v1 (Stage 1 tables + forward-compatible fields)

> The goal is: implement only what Stage 1 needs, but include the fields that prevent painful migrations later.

Concrete SQL migration for Stage 1 lives at `design_docs/migrations/2026_02_03_0100_stage1_core.sql`.

### 9.1 Tables (Stage 1 required)

**`sources`**

* `id` (pk)
* `name`
* `homepage_url`
* `source_type` (journalism, journal, preprint_server, university, government, lab, blog)
* `reliability_tier` (tier1/tier2/tier3 — a transparency bucket, not “good/bad”)
* `terms_notes`
* `active` (bool)
* timestamps

**`source_feeds`**

* `id` (pk)
* `source_id` (fk)
* `feed_url`
* `feed_type` (rss, atom, api)
* `fetch_interval_minutes`
* `last_fetched_at`
* `last_status` (int nullable)
* `error_streak` (int)

**`items`**

* `id` (pk)
* `source_id` (fk)
* `url`
* `canonical_url`
* `title`
* `published_at`
* `fetched_at`
* `author` (nullable)
* `snippet` (nullable, store only if allowed)
* `content_type` (news/press_release/preprint/peer_reviewed/report)
* `paywalled` (nullable bool)
* `language` (default “en” if unknown)
* `raw_ref` (nullable; pointer to raw payload storage or raw JSON row)
* `title_hash`
* `canonical_hash`
* `arxiv_id` (nullable; recommended for Stage 2 clustering quality)
* `doi` (nullable)
* `pmid` (nullable)
* `external_ids` (nullable jsonb)

### 9.2 Indexes/constraints (Stage 1 must-have)

* Unique constraint on `canonical_hash` (idempotency key; `canonical_hash = sha256(normalized_canonical_url)` per `design_docs/decisions.md`; normalization rules: `design_docs/url_normalization_v0.md`)
* Index on `items(published_at desc)`
* Index on `items(source_id, published_at desc)`
* Index on `source_feeds(last_fetched_at)`
* (Optional, recommended) Index on `items(arxiv_id)` where not null
* (Optional, recommended) Index on `items(doi)` where not null
* (Optional, recommended) Index on `items(pmid)` where not null

### 9.3 Recommended ops table (Stage 1 strongly recommended)

**`feed_fetch_logs`** (or `ingestion_runs`)

* feed id, start/end, status, duration, error message, items found/new

---

## 10) Jobs and Processing (Stage 1)

### 10.1 Job: Ingest feeds (worker run)

**Trigger:** schedule / cron, plus optional manual trigger
**Steps:**

1. Select feeds “due” by `last_fetched_at + interval`
2. Fetch with timeout + retry + polite user-agent
3. Parse RSS/Atom into normalized entry objects
4. Canonicalize URL + compute hashes
5. Upsert into `items`
6. Update feed health (`last_fetched_at`, status, `error_streak`)
7. Log fetch run (`feed_fetch_logs`) if enabled

**Acceptance criteria:**

* Running twice does not duplicate Items
* Worker survives malformed feeds without crashing
* Broken feeds visibly show error streak/log

### 10.2 Normalization rules (Stage 1)

* Strip tracking params from URLs (utm_*, fbclid, etc.)
* Normalize URL (scheme/host casing)
* Title normalization for hashing (trim, collapse spaces, lowercasing)

### 10.3 content_type mapping v0 (Stage 1)

Use source-based defaults:

* arXiv/bioRxiv → `preprint`
* NASA/ESA/NOAA/university news → `press_release` (or institutional)
* Science journalism outlets → `news`
* Journal feeds → `peer_reviewed`

(Precision improves later, but the label must exist now.)

---

## 11) API Contract v1 (Stage 1 minimum)

Source of truth for endpoint shapes is `design_docs/openapi.v0.yaml` (Stage 1 uses `/v1/items/feed` and `/v1/sources`; Stage 2+ adds cluster-first `/v1/feed`).

### 11.1 `GET /v1/items/feed` (Stage 1 public feed)

Note: reserve `GET /v1/feed` for Stage 2+ when the feed becomes cluster-first.

**Query params**

* `page` (default 1)
* `page_size` (default 20)
* optional: `source_id`
* optional: `content_type`

**Returns**

* list of Items ordered by `published_at desc` (fallback to fetched_at)

### 11.2 `GET /v1/sources`

Returns sources + feed health snapshot:

* source name, active
* each feed last fetched, error streak, last status

### 11.3 Stage 1 security baseline

* Basic rate limiting on public endpoints
* Admin endpoints behind an admin token or basic auth (v0 recommendation: `X-Admin-Token`, see `design_docs/openapi.v0.yaml`)

---

## 12) Observability & Quality Gates (Stage 1)

### 12.1 Operational metrics to track from day one

* Fetch success rate per feed
* Items added per run
* Average fetch duration
* Error types (timeout, 403, parse error)
* “Stale feed” alerts (no successful fetch in X hours)

### 12.2 Data sanity checks (Stage 1 recommended)

* % items missing title/url/published_at
* Duplicate rate by source
* Spike detection (garbage feed floods)

Optional “quarantine” later: auto-disable or flag feeds producing garbage.

---

## 13) Stage 1 Execution Plan (Ticket Board)

### Milestone A — Skeleton & Dev Environment

* **ST1-A1** Repo layout + shared types/schemas
* **ST1-A2** Docker Compose (Postgres + services)
* **ST1-A3** CI (lint/typecheck/tests) *(recommended)*

### Milestone B — DB Schema + Seed Data

* **ST1-B1** Migrations: sources/feeds/items (+ logs)
* **ST1-B2** Seed script idempotent (sources + feeds; format: `design_docs/source_pack_v0.md`)
* **ST1-B3** Curated source pack v0 JSON (≥10 sources + notes; format: `design_docs/source_pack_v0.md`)

### Milestone C — Ingestion Worker v0

* **ST1-C1** Fetcher with retries, timeouts, per-domain concurrency
* **ST1-C2** RSS/Atom parser + unified entry model
* **ST1-C3** Canonical URL normalization + hashing
* **ST1-C4** Item upsert idempotent + feed health updates
* **ST1-C5** Worker “run-once” + due-feed scheduling
* **ST1-C6** Feed fetch logs *(strongly recommended)*

### Milestone D — Normalization & Labeling

* **ST1-D1** content_type mapping v0 + language defaults
* **ST1-D2** Data quality checks job *(recommended)*

### Milestone E — API v0

* **ST1-E1** `GET /v1/items/feed` paginated, schema validated
* **ST1-E2** `GET /v1/sources` health snapshot
* **ST1-E3** Rate limiting + basic security

### Milestone F — Web UI v0

* **ST1-F1** Feed page renders from API + click-out
* **ST1-F2** Sources health page *(recommended)*

### Milestone G — Admin v0

* **ST1-G1** Admin auth gate
* **ST1-G2** Admin: manage sources/feeds (disable/edit/add)
* **ST1-G3** Admin: run ingestion now *(optional but great)*

### Milestone H — Deployment & Prod Readiness

* **ST1-H1** Deploy DB + API + Worker schedule + Web
* **ST1-H2** Backups + health checks *(recommended)*

### Milestone I — Hardening (still Stage 1)

* **ST1-I2** Concurrency safety (overlapping runs)
* **ST1-I1** Conditional requests (ETag/Last-Modified)
* **ST1-I3** Quarantine mode *(optional)*

#### Recommended build order (minimize rework)

1. A1 → A2 → B1 → B2 → B3
2. C1 → C2 → C3 → C4 → C5 → C6 → D1
3. E1 → E2 → F1 (now you have a usable product)
4. G1 → G2 (admin maintainability)
5. H1 (deploy) → I2 (concurrency) → H2/I1/D2

---

## 14) Stage 1 “Definition of Done” (Explicit checklist)

You can move to Stage 2 when all are true:

**Data + ingestion**

* [ ] ≥10 sources ingest successfully end-to-end
* [ ] Worker is idempotent (no dupes on rerun)
* [ ] Feed freshness is acceptable (ingestion schedule running in prod)
* [ ] Per-feed health visible (last fetched + error streak, ideally logs)

**API**

* [ ] `/v1/items/feed` returns stable pagination and correct sorting
* [ ] `/v1/sources` returns health snapshot
* [ ] Basic rate limiting present

**Web**

* [ ] Latest feed renders correctly from API
* [ ] Cards show source + time + content_type badge + click-out
* [ ] No broken UX when snippet missing

**Admin & ops**

* [ ] You can disable a broken feed without redeploying
* [ ] DB backups enabled (or documented plan if local-only)
* [ ] Health checks exist (at least a simple endpoint/log view)

---

# 15) What’s Needed Before Starting Stage 2?

If you complete Stage 1’s “Definition of Done,” you are *functionally ready* to start Stage 2. There are only a few additional “Stage 2 readiness” items worth ensuring so Stage 2 doesn’t get bogged down:

## 15.1 Stage 2 readiness checklist (recommended)

1. **Source set is stable enough**

   * You don’t need 200 sources, but you should have a mix:

     * at least a few high-quality journalism sources
     * at least one or two preprint feeds
     * at least one institutional source
   * And you know which ones are noisy.

2. **URL normalization is trustworthy**

   * Stage 2 clustering depends on canonical URLs + title hashes.
   * If canonicalization is inconsistent, clustering quality suffers immediately.

3. **You’ve decided where clustering logic lives**

   * Keep Stage 2 clustering as a worker job that writes to DB tables:

     * `story_clusters` and `cluster_items`
   * Don’t do clustering “live” at request time.

4. **You can inspect and debug**

   * Even a basic admin view for “recent items by source” helps.
   * You’ll need visibility when clusters merge incorrectly.

## 15.2 Do we need anything else before Stage 2?

Not structurally. If Stage 1 is done, you can move on.

The only optional “nice-to-have” before Stage 2 that can save you pain:

* **Feed fetch logs (ST1-C6)** and **concurrency safety (ST1-I2)**
  These dramatically reduce debugging time when you start clustering.

---

# 16) Stage 2 Preview (so Stage 2 planning is smooth)

Stage 2 will add:

* `story_clusters` + `cluster_items`
* near-duplicate detection
* cluster assignment job
* “Latest vs Trending” at the **cluster level**
* search v1 (cluster-first)
* basic topic tagging v0 (even rule-based)

Everything you built in Stage 1 stays the foundation.
