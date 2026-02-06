## Roadmap overview

This file is the **stage-by-stage roadmap**. Related detailed docs:

* `design_docs/project_motivation.md` (the “why” + shared vocabulary)
* `design_docs/decisions.md` (locked choices that remove blockers)
* `design_docs/stage0.md` (PRD + tech spec foundations)
* `design_docs/stage1.md` (ingestion + storage + minimal web)
* `design_docs/stage2.md` (clusters/dedup/trending/search/topics + DB migrations + clustering QA)
* `design_docs/stage3.md` (Stage 3 UI system for the understanding layer; includes the implementation-ready component spec)
* `design_docs/frontend_handoff.md` (single handoff doc for implementing the Next.js frontend)
* `design_docs/frontend/` (frontend architecture, components, data layer, PWA, testing, accessibility, SEO, error/empty states)
* `design_docs/stage3_backend.md` (Stage 3 backend: schema + enrichment job + guardrails)
* `design_docs/stage4.md` (update tracking + lineage)
* `design_docs/stage5.md` (accounts + personalization)
* `design_docs/stage6.md` (notifications + digests)
* `design_docs/stage7.md` (mobile PWA + performance + scaling)
* `design_docs/stage8.md` (governance + editorial tooling)
* `design_docs/stage9.md` (platform hardening + search/ranking upgrades)
* `design_docs/stage10.md` (mature ecosystem: entities + experiments + extensibility)
* `design_docs/source_pack_v0.md` (seed format for sources + feeds)
* `design_docs/url_normalization_v0.md` (deterministic canonical URLs + idempotency)

---

## Stage 0 — Product + system foundations

**Goal:** Freeze what you’re building so implementation isn’t ambiguous.

**Ship/decide:**

* PRD (users, success metrics, non-goals like no full-text republishing unless licensed)
* Info architecture: Feed → Topic → StoryCluster → Item → Paper
* Core UX wireframes: feed card, story page, topic page, search, settings
* Source policy + paywall rules + scraping rules + whitelists
* Label spec: content_type (news/press release/preprint/peer-reviewed/report), reliability tier, banners (“preprint not peer reviewed”)
* Safety/quality rules: uncertainty required, anti-hype flags required, medical claims = report not advise
* Technical architecture doc + failure handling (retries/dedupe/idempotency)
* Data model v1: Source, Item, StoryCluster, Topic, GlossaryEntry, LineageNode, UpdateLog, UserPrefs, EngagementEvent
* API contract v1 (stable shape over stages):
  * Stage 1: `/v1/items/feed`, `/v1/sources`
  * Stage 2+: `/v1/feed`, `/v1/clusters/{id}`, `/v1/topics/{id}`, `/v1/search`
  * Stage 5+: `/v1/events`, `/v1/user/prefs`
* Observability plan: ingestion health, clustering merge rates, citation/low-confidence flags, ranking metrics

**Exit:** One doc answers “what does it do + how does it work + what structures enable it?”

---

## Stage 1 — Ingestion + storage + minimal web client

**Goal:** Reliable “science news engine” + basic UI.

**User-facing:**

* Web latest feed
* Source filter + basic categories
* Cards link out to original source

**Backend:**

* RSS + a few APIs (e.g., arXiv + key org feeds)
* Raw payload storage + normalized items (title/url/published_at/source/snippet/content_type)
* Admin: add/remove sources, pause source, view fetch errors
* DB + indexes for date/source queries
* API: `GET /v1/items/feed`, `GET /v1/sources` (Stage 2+ introduces cluster-first `GET /v1/feed`)

**Exit:** Stable ingestion + sources can be added without code changes.

---

## Stage 2 — Dedup + StoryClusters + trending/latest + search v1 + topic pages v1

**Goal:** Turn “list of links” into organized stories.

**User-facing:**

* Clustered feed (cluster cards: headline, #sources, last updated, content-type badge)
* Latest + Trending tabs
* StoryCluster pages (canonical story + coverage list)
* Topic pages v1 (basic tags → list of clusters)
* Search v1 (keyword across clusters/topics/sources)

**Backend:**

* Exact + near-dup detection
* Clustering (StoryCluster + join table)
* Topic extraction v1 (source tags + lightweight entity/keyword extraction)
* Trending score v1 (source count + velocity + recency decay)
* Postgres full-text search (good enough early)

**Exit:** Duplicates mostly gone; clusters feel “one story, many sources.”

---

## Stage 3 — Understanding layer v1 + glossary + method badges + trust/uncertainty + anti-hype

**Goal:** Differentiator: explain science clearly and responsibly.

**User-facing on StoryCluster page:**

* Takeaway (1 sentence)
* Intuition (default) + Deep Dive (expand)
* Evidence links grouped by type
* Trust box (preprint vs peer-reviewed vs press release vs news; independent source count)
* Uncertainty framing (“early / growing / established” + “what could change this?”)
* Method badges (observational/experiment/simulation/clinical/benchmark/etc.)
* Anti-hype flags (mice only, small sample, press release only, etc.)
* Just-in-time glossary tooltips (tap terms for short defs)

**Backend:**

* Enrichment pipeline writing structured fields (not one blob)
* Guardrails: citations required; low confidence → fallback to minimal + links
* Glossary system + term resolver

**Exit:** Non-experts understand via Intuition; technical readers satisfied by Deep Dive.

---

## Stage 4 — Update tracking + “what changed” + lineage timelines

**Goal:** Make science a living map, not isolated posts.

**User-facing:**

* Cluster update log (“Updated on YYYY-MM-DD because …”)
* Diff-style “Previously… Now… Because…”
* Topic timelines / lineage graph (builds on / contradicts / replaces-in-some-settings)
* Follow a story (watch cluster; notifications come later)

**Backend:**

* Cluster versioning (snapshots of takeaway/explanations/uncertainty/flags)
* Change summarizer with citations
* Lineage graph model (nodes + edges + evidence links)
* Relationship rules: no edges without explicit support (citations/strong metadata/curated overrides)

**Exit:** Users can track evolution over time without rereading everything.

---

## Stage 5 — Accounts + personalization

**Goal:** Make it sticky without creating a filter bubble.

**User-facing:**

* Accounts
* Follow topics; block sources
* Saves/bookmarks
* Reading level default (Intuition-first vs Deep Dive-first)
* Personalized “For you” feed + neutral “Latest”

**Backend:**

* User prefs tables
* Event logging (click/save/hide/follow)
* Simple recommender v1 (topic match + recency + quality tiers; understandable logic)

**Exit:** Users can tune the experience and reliably get more of what they care about.

---

## Stage 6 — Notifications + digests

**Goal:** Bring users back usefully, not addictively.

**User-facing:**

* Topic alerts, story update alerts (“what changed”), optional trending alerts
* Daily/weekly digest (“Top developments in your topics”)
* Settings: frequency, quiet hours, thresholds

**Backend:**

* Scheduler + rate limiting + dedupe
* “Meaningful change” thresholds (new paper, contradiction, confidence shift)
* Templates: takeaway + source types + link

**Exit:** Notifications feel high-signal and controllable.

---

## Stage 7 — Mobile app + performance + scaling upgrades

**Goal:** Full app experience + speed + reliability.

**User-facing:**

* Mobile app (or high-quality cross-platform/PWA)
* Offline saved reading
* Smooth topic/story navigation
* Faster search + better discovery

**Backend/infra:**

* Cache layer (e.g., Redis)
* Job queue with retries/backoff
* Optional vector search for clustering + semantic search
* Monitoring + alerts + performance budgets

**Exit:** App feels fast, stable, and trustworthy at real scale.

---

## Stage 8 — Governance + editorial tooling (“trust flywheel”)

**Goal:** Quality doesn’t collapse as you grow.

**Features/tools:**

* Corrections mechanism (“updated because earlier summary was incomplete”)
* Source quality audits (auto + manual)
* Editorial overrides: merge/split, pin best explanation, fix topic tags, adjust lineage edges
* Feedback hooks (“confusing”, “overstated”)

**Exit:** You can expand sources/features without turning into hype sludge.

---

## Stage 9 — Platform hardening + search/ranking upgrades

**Goal:** Production-grade ops and better retrieval.

**Do:**

* Strong observability + ingestion SLAs
* Cost controls (caching/batching/queue tuning)
* Search ranking improvements; optional vector/hybrid search
* Automated eval harness: citation coverage, “no unsupported claims”, label consistency (peer-reviewed vs arXiv)

**Exit:** Fewer incidents, predictable costs, measurable quality.

---

## Stage 10 — Mature ecosystem (polish + extensibility)

**Goal:** Future-proof: new formats + richer knowledge graph.

**Add:**

* Richer entity following (authors/institutions/models)
* Deeper lineage/knowledge graph exploration
* A/B testing framework (ranking + UX)
* More client polish (widgets, deep links, accessibility)

**Exit:** You can keep shipping without rewrites.

---

## Cross-stage decisions (locked for v0)

These are resolved in `design_docs/decisions.md` and should be treated as “locked defaults” unless intentionally changed:

* **Text storage + licensing:** metadata-first; no paywalled full text; whitelisted sources for richer text.
* **IDs:** UUIDs across Postgres.
* **Canonical URL normalization:** deterministic rules + per-source overrides; hash is the idempotency key.
* **Understanding fields storage:** nullable columns on `story_clusters` + per-section supporting Item IDs.
* **Meaningful change thresholds:** defined once and reused for update logs + future notifications.
* **Lineage edges:** always require explicit evidence.
