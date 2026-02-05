Below are two clean, build-ready sections you can treat as your **Stage 0 package** (kept together in this file):

1. **PRD v0.1** (Product Requirements Doc)
2. **Tech Spec v0.1** (Architecture + Schemas + Jobs + APIs + v0 heuristics)

They’re detailed enough to start Stage 1 without ambiguity, while still staying at the “main idea per stage” level.

For the “why” behind the product (problem statement + wedge), see `design_docs/project_motivation.md`. Locked cross-stage decisions (IDs, text policy, canonical URL rules, etc.) are in `design_docs/decisions.md`. Stage numbering across `design_docs/` follows `design_docs/implementation_plan_overview.md`.

---

# Curious Now — PRD v0.1 (Science News + Understanding Layer)

## 1) Product overview

### 1.1 Vision

Create a science news app that:

* **Aggregates** from many sources responsibly,
* **Clusters** coverage into canonical stories,
* **Explains** technical content in two layers (**Intuition → Deep Dive**),
* **Shows trust & uncertainty** transparently,
* **Tracks updates and lineage** (how ideas/models evolve).

### 1.2 One-line value proposition

“Science news you can actually understand—then go deeper—with trust and updates built in.”

### 1.3 Key differentiators

1. Canonical **StoryClusters** (deduped, multi-source coverage)
2. **Takeaway + Intuition + Deep Dive** (progressive complexity)
3. Built-in **Trust box** + **Uncertainty framing**
4. **Update tracking** (“What changed since last time?”)
5. **Lineage timelines** (e.g., BERT → ALBERT)

---

## 2) Target users & jobs-to-be-done

### 2.1 Personas

**P1 — Curious Generalist**

* Wants quick understanding + “why it matters”
* Doesn’t want jargon and hype

**P2 — Student / Learner**

* Wants background and tooltips while reading
* Learns by exploring terms and related topics

**P3 — Technical Reader**

* Wants methods, assumptions, limitations
* Wants paper link and multi-source context fast

### 2.2 Primary JTBD

* “Tell me the takeaway in 10 seconds.”
* “Explain the intuition; let me opt into deep details.”
* “Help me calibrate trust and uncertainty.”
* “Let me follow a topic and see what changed over time.”
* “Show model/paper evolution as a timeline.”

---

## 3) Scope

### 3.1 In-scope (full vision)

**Content organization**

* Multi-source ingestion (RSS/APIs first)
* Normalization + dedupe + clustering into StoryClusters
* Topic taxonomy and topic pages
* Search across clusters/topics

**Understanding & learning**

* Takeaway (1 sentence)
* Intuition section (plain language)
* Deep Dive section (technical but readable)
* Evidence links grouped by content type
* Glossary tooltips (“just in time” learning)
* Method badges (observational/experiment/simulation/etc.)
* Anti-hype flags (mice-only, small sample, press-release-only, etc.)

**Trust & uncertainty**

* Trust box: source types and diversity
* Confidence band: early/growing/established
* “What could change this?” section

**Time & evolution**

* Update tracking on clusters (“what changed” + update log)
* Lineage timelines (papers/models/methods)

**Personalization & retention**

* Accounts
* Follow topics; block sources; save stories
* Reading mode default (Intuition-first vs Deep-first)
* Notifications & digests (topic updates + story updates)

**Platforms**

* Web app first; mobile app later; one shared API

### 3.2 Out-of-scope (explicit non-goals)

* Republishing full paywalled content
* “Becoming a journal” (peer review / endorsement)
* Medical advice (strictly reporting + uncertainty)
* Infinite personalization early (start simple, transparent ranking)

---

## 4) Content policy and labeling requirements

### 4.1 Source types & content types

Every Item and StoryCluster must be labeled clearly.

**Source types** (what kind of publisher it is; stored on `sources.source_type`)

* journalism outlet
* journal
* preprint server
* university / institution
* government
* lab
* blog

**Content types** (what the Item is; stored on `items.content_type`)

* `news` (journalism article)
* `press_release` (institutional news / PR)
* `preprint`
* `peer_reviewed`
* `report` (gov/NGO/standards)

**Rules**

* Preprints always show: “Not peer reviewed”
* Press releases show: “Press release (may be promotional)”
* Paywalled: show metadata + link out (don’t store/display full text unless permitted)

### 4.2 “Source-first” requirement

Every StoryCluster page must include:

* a list of sources (Evidence panel)
* a link out to originals
* citations for key statements in explanations (where feasible)

---

## 5) UX requirements (screens + acceptance criteria)

### 5.1 Feed screen

**Purpose:** discovery and daily usage.

**Components**

* Tabs: Latest | Trending | (For You later)
* Filters: topic, content type, time range (later), source (later)
* Card fields:

  * title
  * badges (preprint / peer_reviewed / press_release / news)
  * source count
  * “updated X ago”
  * optional: one-line takeaway (when available)

**Acceptance criteria**

* No obvious duplicates in the feed (dedupe works)
* Trending feels different from Latest (velocity-based)
* Tap opens StoryCluster page in < 1s perceived (with caching)

---

### 5.2 StoryCluster page (core experience)

**Purpose:** understand one story with trust and depth.

**Layout requirements**

1. **Takeaway** (1 sentence)
2. **Badges** (content type + method badge if known)
3. **Intuition** (default visible)
4. **Deep Dive** (expandable)
5. Assumptions + Limitations bullets (when available)
6. Trust box + Confidence band
7. Anti-hype flags (if any)
8. Evidence links grouped by source type
9. Update tracking section (“What changed” + update log)
10. (Later) “Follow story”

**Acceptance criteria**

* Intuition is understandable without domain expertise (jargon minimized)
* Deep Dive contains method/assumptions/limitations (technical readers satisfied)
* Every StoryCluster has evidence links (minimum: 1)
* Preprint clusters show disclaimer
* Update log appears once the cluster changes after first publish

---

### 5.3 Topic page

**Purpose:** exploration + long-term learning.

**Components**

* Topic summary (short)
* Latest clusters
* Trending in topic
* Related topics
* **Lineage timeline** (when available)
* Follow topic button (later)

**Acceptance criteria**

* Topics are consistent and not noisy (taxonomy + aliases work)
* Timeline relationships are labeled (extends/compresses/contradicts/etc.)
* Timeline edges link to evidence sources

---

### 5.4 Search

**Purpose:** find stories/topics quickly.

**Requirements**

* Search across: clusters, topics (and later entities/models)
* Results grouped by type (clusters/topics)
* Filters: time, content type (later)

**Acceptance criteria**

* Search finds the cluster even if user searches a synonym (via aliases)
* Results are deduped (cluster-level results first)

---

### 5.5 Settings / Profile (later stage but designed now)

**Requirements**

* Reading default: Intuition-first vs Deep-first
* Followed topics
* Blocked sources
* Notification settings and quiet hours

**Acceptance criteria**

* Changes immediately affect feed output (server-side filtering/ranking)

---

## 6) Success metrics (v0)

**Acquisition/retention**

* Day-1 and Day-7 retention
* “Return visits per week”

**Engagement quality**

* Saves/bookmarks per 100 views
* “Helpful / Confusing” feedback rate (optional early)
* Scroll depth or time-on-cluster page (privacy-respecting)

**Trust signals**

* Low hide rate on trusted sources
* High “read original” click-through for deep readers

**Operational**

* Ingestion success rate by source
* Time from source publish to appearing in app

---

## 7) Rollout plan (high level)

* Stage 1: ingestion + storage + minimal web feed
* Stage 2: StoryClusters + dedup + trending + topic pages + search v1
* Stage 3: understanding layer v1 (takeaway/intuition/deep dive) + trust/uncertainty + glossary + method badges + anti-hype
* Stage 4: update tracking (“what changed”) + lineage timelines
* Stage 5: accounts + personalization (follow topics, block sources, saves)
* Stage 6: notifications + digests
* Stage 7: mobile app (or PWA) + scaling/performance upgrades
* Stage 8: governance + editorial tooling
* Stage 9: platform hardening + search/ranking upgrades
* Stage 10: mature ecosystem (polish + extensibility)

---

---

# Tech Spec v0.1 — Architecture, Data Contracts, Jobs, APIs, Heuristics

## 1) System architecture overview

### 1.1 Recommended v0 architecture (simple, scalable later)

**One backend service + workers (same repo), one DB**

* **API Server**

  * serves feed/search/cluster/topic
  * handles user prefs and event logging
* **Ingestion Worker**

  * fetch RSS/APIs on schedule
* **Processing Worker**

  * normalization, dedupe, clustering
  * enrichment (explanations, topics/entities, flags)
  * update log generation
* **(Later) Notification Worker**

  * digests + push/email

### 1.2 Storage

* **Postgres** as primary DB (recommended)
* **Object storage** (later) for raw payload archives (optional in v0)
* **Redis cache** (later) for feed + cluster response caching

### 1.3 Time + IDs

* Store time in ISO 8601 UTC (`timestamptz`)
* IDs: UUIDs (locked in `design_docs/decisions.md`).

---

## 2) Data model (schemas + indexes)

Below is “implementable high level”: field names + types + key indexes.

### 2.1 `sources`

* `id` (pk)
* `name` (text)
* `homepage_url` (text)
* `source_type` (enum: journalism, journal, preprint_server, university, government, lab, blog)
* `reliability_tier` (enum: tier1, tier2, tier3) **(tier = transparency bucket, not “good/bad”)**
* `terms_notes` (text)
* `active` (bool)
* `created_at`, `updated_at`

**Indexes**

* `active`

### 2.2 `source_feeds`

* `id` (pk)
* `source_id` (fk)
* `feed_url` (text)
* `feed_type` (enum: rss, atom, api)
* `fetch_interval_minutes` (int)
* `last_fetched_at` (timestamptz)
* `last_status` (int)
* `error_streak` (int)

**Indexes**

* `(source_id)`
* `(last_fetched_at)`

### 2.3 `items`

* `id` (pk)
* `source_id` (fk)
* `url` (text)
* `canonical_url` (text)
* `title` (text)
* `published_at` (timestamptz)
* `fetched_at` (timestamptz)
* `author` (text nullable)
* `snippet` (text nullable)
* `content_type` (enum: news, press_release, preprint, peer_reviewed, report)
* `paywalled` (bool nullable)
* `language` (text, e.g. "en")
* `raw_ref` (text nullable) (pointer/key for raw payload storage)
* `title_hash` (text) (normalized hash)
* `canonical_hash` (text) (canonical_url hash)
* `arxiv_id` (text nullable)
* `doi` (text nullable)
* `pmid` (text nullable)
* `external_ids` (jsonb nullable)

**Indexes**

* unique `(canonical_hash)` (primary idempotency key; see `design_docs/decisions.md`)
* optional unique `(canonical_url)` when safe/clean (helpful but not relied on)
* `(published_at desc)`
* `(source_id, published_at desc)`
* `(title_hash)`
* `(arxiv_id)` where not null
* `(doi)` where not null
* `(pmid)` where not null
* GIN on `external_ids` if used

### 2.4 `story_clusters`

Stage 2 core fields:

* `id` (pk)
* `status` (enum: active, merged, quarantined)
* `created_at`, `updated_at`
* `canonical_title` (text)
* `representative_item_id` (fk → items.id, nullable)
* `distinct_source_count` (int)
* `distinct_source_type_count` (int)
* `item_count` (int)
* `velocity_6h` (int)
* `velocity_24h` (int)
* `trending_score` (float)
* `recency_score` (float)
* `metrics_extra` (jsonb) (future-proofing)

Stage 3+ understanding fields (nullable; decided as columns on `story_clusters` in `design_docs/decisions.md`):

* `takeaway` (text)
* `takeaway_supporting_item_ids` (jsonb array of item IDs)
* `summary_intuition` (text)
* `summary_intuition_supporting_item_ids` (jsonb array of item IDs)
* `summary_deep_dive` (text)
* `summary_deep_dive_supporting_item_ids` (jsonb array of item IDs)
* `assumptions` (jsonb array of strings)
* `limitations` (jsonb array of strings)
* `confidence_band` (enum: early, growing, established)
* `what_could_change_this` (jsonb array of strings)
* `method_badges` (jsonb array)
* `anti_hype_flags` (jsonb array)

**Indexes**

* `(updated_at desc)`
* `(trending_score desc)`
* GIN index on `metrics_extra` if needed later

### 2.5 `cluster_items`

* `cluster_id` (fk)
* `item_id` (fk)
* `role` (enum: primary, supporting, background)
* `added_at` (timestamptz)

**Indexes**

* unique `(cluster_id, item_id)`
* `(item_id)` for reverse lookup

### 2.6 `cluster_redirects` (recommended; stable URLs on merges)

When a cluster is merged into another cluster, keep old IDs resolvable:

* `id` (pk)
* `from_cluster_id` (fk → story_clusters.id) **unique**
* `to_cluster_id` (fk → story_clusters.id)
* `redirect_type` (enum: merge)
* `created_at`

**Rule:** `GET /v1/clusters/{id}` for a merged cluster returns a redirect response pointing to `to_cluster_id` (see `design_docs/openapi.v0.yaml`).

### 2.7 `topics`

* `id` (pk)
* `name` (text)
* `description_short` (text nullable)
* `aliases` (jsonb) (array)
* `parent_topic_id` (fk nullable)

Recommended for stable URLs when topics are merged (Stage 8):

**`topic_redirects`**

* `id` (pk)
* `from_topic_id` (fk → topics.id) **unique**
* `to_topic_id` (fk → topics.id)
* `redirect_type` (enum: merge)
* `created_at`

**Rule:** `GET /v1/topics/{id}` for a merged topic returns a redirect response pointing to `to_topic_id` (see `design_docs/openapi.v0.yaml`).

**Indexes**

* unique `(name)`
* GIN on `aliases`

### 2.8 `cluster_topics`

* `cluster_id` (fk)
* `topic_id` (fk)
* `score` (float) (confidence of tag)
* `added_at`
* `assignment_source` (auto/editor; Stage 8)
* `locked` (bool; Stage 8)

**Indexes**

* `(topic_id, cluster_id)`
* unique `(cluster_id, topic_id)`

### 2.9 `glossary_entries`

* `id` (pk)
* `term` (text)
* `definition_short` (text)
* `definition_long` (text nullable)
* `related_topic_ids` (jsonb nullable)

**Indexes**

* unique `(term)`

### 2.10 Update tracking (Stage 4)

**`cluster_revisions`**

* `id` (pk)
* `cluster_id` (fk)
* `created_at`
* snapshot fields (copy from cluster at the time): `takeaway`, `summary_intuition`, `summary_deep_dive`, `confidence_band`, `method_badges`, `anti_hype_flags`
* `trigger` (enum: new_item, merge, split, quarantine, unquarantine, manual_override, correction)

**`update_log_entries`**

* `id` (pk)
* `cluster_id` (fk)
* `created_at`
* `change_type` (enum: new_evidence, contradiction, refinement, merge, split, quarantine, unquarantine, correction)
* `previous_revision_id` (fk)
* `new_revision_id` (fk)
* `summary` (text)
* `diff` (jsonb: previously/now/because arrays)
* `supporting_item_ids` (jsonb array)

**Indexes**

* `(cluster_id, created_at desc)`

### 2.11 Lineage graph (Stage 4)

**`lineage_nodes`**

* `id` (pk)
* `node_type` (enum: paper, model, dataset, method)
* `title` (text)
* `external_url` (text)
* `published_at` (timestamptz nullable)
* `external_ids` (jsonb nullable)
* `topic_ids` (jsonb nullable)

**`lineage_edges`**

* `id` (pk)
* `from_node_id` (fk)
* `to_node_id` (fk)
* `relation_type` (enum: extends, improves, compresses, replaces_in_some_settings, contradicts, orthogonal)
* `evidence_item_ids` (jsonb)
* `notes_short` (text nullable)

### 2.12 Users & personalization (Stage 5)

**`users`**

* `id` (pk)
* `created_at`
* `email_normalized` (unique)
* `email_raw` (optional)
* `last_login_at`
* timestamps

**`user_sessions`** (v0: cookie-backed sessions)

* `id` (pk)
* `user_id` (fk)
* `session_token_hash` (unique)
* `expires_at`, `revoked_at`, `last_seen_at`
* timestamps

**`auth_magic_link_tokens`** (v0: email magic link login)

* `id` (pk)
* `user_id` (fk)
* `token_hash` (unique)
* `expires_at`, `used_at`
* timestamps

**`user_prefs`**

* `user_id` (pk/fk)
* `reading_mode_default` (enum: intuition, deep)
* `notification_settings` (jsonb)
* timestamps

**`user_topic_follows`**

* `user_id` (fk)
* `topic_id` (fk)
* `created_at`

**`user_source_blocks`**

* `user_id` (fk)
* `source_id` (fk)
* `created_at`

**`user_cluster_saves`**

* `user_id` (fk)
* `cluster_id` (fk)
* `created_at`

**`user_cluster_hides`**

* `user_id` (fk)
* `cluster_id` (fk)
* `created_at`

**`engagement_events`**

* `id` (pk)
* `user_id` (fk nullable)
* `client_id` (uuid nullable; optional for anonymous analytics)
* `event_type` (enum; see `design_docs/stage5.md` / Stage 5 migration)
* `cluster_id` (fk nullable)
* `item_id` (fk nullable)
* `topic_id` (fk nullable)
* `meta` (jsonb)
* `created_at`

### 2.13 `cluster_search_docs` (Stage 2)

* `cluster_id` (pk/fk)
* `search_text` (text)
* `search_tsv` (tsvector)
* `updated_at`

### 2.14 `cluster_assignment_logs` (Stage 2)

* `id` (pk)
* `created_at`
* `item_id` (fk)
* `decided_cluster_id` (fk)
* `decision` (created_new | attached_existing | merged_clusters)
* `candidate_cluster_ids` (jsonb)
* `score_breakdown` (jsonb)
* `threshold_used` (float nullable)

### 2.15 Notifications & digests (Stage 6)

**`user_cluster_watches`**

* `user_id` (fk)
* `cluster_id` (fk)
* `created_at`

**`notification_jobs`**

* durable notification queue + delivery record
* `user_id` (fk)
* `channel` (email/in_app/push)
* `notification_type` (cluster_update/topic_digest)
* `status` (queued/sending/sent/error/canceled)
* `dedupe_key` (unique)
* `scheduled_for`, `sent_at`
* `payload` (jsonb), plus optional rendered subject/body for debugging

### 2.16 Vector search (optional; Stage 7+)

If implementing pgvector-based semantic search (optional), add:

**`cluster_embeddings`**

* `cluster_id` (pk/fk)
* `embedding` (vector)
* `embedding_model`
* `source_text_hash` (detect when to recompute)
* timestamps

### 2.17 Governance (Stage 8)

**`feedback_reports`**

* end-user feedback for quality improvements (auth optional)
* `feedback_type`, `status`, target references (`cluster_id`/`item_id`/`topic_id`)

**`editorial_actions`**

* append-only audit log for merges/splits/corrections/topic fixes/lineage fixes
* links to targets and optional `supporting_item_ids`

### 2.18 Entities + experimentation (Stage 10)

**Entities**

* `entities` (+ `entity_aliases`, `entity_redirects`)
* `cluster_entities` (cluster → entity mapping; supports `locked=true` for editorial)
* `entity_edges` (evidence-backed relationships between entities)
* `user_entity_follows`

**Experimentation**

* `experiments`, `experiment_variants`, `experiment_assignments`
* `feature_flags`

---

## 3) Processing jobs (what runs, when, and what it outputs)

### 3.1 Job: Feed ingestion

**Trigger:** schedule per feed
**Steps:**

1. fetch feed URL
2. parse entries
3. create/update Items (idempotent by `canonical_hash`, derived from normalized canonical_url)
4. emit “new_item” events for downstream processing

**Outputs:**

* new/updated `items`
* ingestion logs/metrics

---

### 3.2 Job: Normalize item

**Trigger:** on item create/update
**Steps:**

* canonical URL cleanup (remove tracking params)
* title normalization (whitespace/case cleanup)
* compute `title_hash`, `canonical_hash`
* content_type classification v0 (rules based on source + URL patterns)

**Outputs:**

* normalized item fields

---

### 3.3 Job: Cluster assignment (dedupe + clustering v0)

**Trigger:** normalized item ready
**Steps:**

1. check exact duplicates via canonical_hash
2. find candidate clusters from recent window (e.g., last 14 days)
3. similarity check v0:

   * title similarity + shared entities/keywords
4. assign to best cluster or create new
5. update cluster counters + timestamps (distinct source counts, item_count, updated_at, velocity windows as available)

**Outputs:**

* `cluster_items` row
* updated `story_clusters` counters/scores (and `metrics_extra` if used)
* optional “merge” action if needed (with caution)

---

### 3.4 Job: Enrichment (Understanding layer)

**Trigger:** cluster created OR cluster updated with meaningful new evidence
**Steps:**

* generate `takeaway`
* generate `summary_intuition` (plain language)
* generate `summary_deep_dive` (method & reasoning)
* attach supporting evidence (per-section Item IDs)
* extract assumptions, limitations, what-could-change
* method badges detection
* anti-hype flags detection
* glossary term linking
* confidence band v0 decision

**Outputs:**

* updated `story_clusters` fields (including `*_supporting_item_ids` for citations)
* cluster-level glossary entries/links (v0: a list of terms for tooltips; no inline markup required)

**Fallback rule (critical):**
If not enough accessible text (only headline):

* do **not** fabricate details
* show minimal: title + source list + “Insufficient accessible detail to summarize reliably.”

---

### 3.5 Job: Update tracking (“What changed”) (Stage 4)

**Trigger:** after enrichment on cluster update (or merges/corrections)
**Steps:**

1. decide if the change is “meaningful” (new peer-reviewed/preprint/report evidence, confidence shift, anti-hype flag change, contradiction, merge, correction)
2. create a new `cluster_revisions` snapshot
3. generate `update_log_entries.summary` + `update_log_entries.diff` (Previously/Now/Because)
4. attach `supporting_item_ids` for every update (no uncited diffs)
5. fallback: if citations can’t be produced safely, emit a minimal `new_evidence` update that links out (no interpretive diff)

**Outputs:**

* `cluster_revisions`
* `update_log_entries`

---

### 3.6 Job: Topic tagging

**Trigger:** after enrichment or periodically
**Steps v0:**

* source-provided tags + curated keyword rules + aliases
* assign scores and write to `cluster_topics`

---

### 3.7 Job: Lineage builder (Stage 4)

**Trigger:** scheduled + on certain topic clusters
**Allowed relationships must be evidence-backed** (no invented edges).

**Outputs:**

* `lineage_nodes`, `lineage_edges`

---

### 3.8 Job: Ranking computation

**Trigger:** periodic (e.g., every 10 minutes) or on update
Compute:

* `latest` ordering: updated_at desc
* `trending` score: velocity + diversity + recency decay
* later personalization signals

---

## 4) API contract (endpoints + response examples)

Source of truth for the full contract is `design_docs/openapi.v0.yaml`. This section provides the stage-oriented overview + illustrative examples.

All responses should be stable and “client-ready.”

### 4.1 `GET /v1/items/feed` (Stage 1)

Stage 1 serves a simple Item feed. Stage 2+ keeps this endpoint for debugging/internal use (cluster-first becomes the public feed).

**Query**

* `page=...`
* `page_size=...`
* `source_id=...` optional
* `content_type=...` optional

**Response example**

```json
{
  "page": 1,
  "results": [
    {
      "item_id": "11111111-1111-1111-1111-111111111111",
      "title": "NASA announces Artemis II crew for a lunar flyby mission",
      "url": "https://...",
      "canonical_url": "https://...",
      "published_at": "2026-01-15T14:00:00Z",
      "fetched_at": "2026-01-15T14:02:10Z",
      "source": {"source_id": "22222222-2222-2222-2222-222222222222", "name": "NASA"},
      "content_type": "press_release",
      "snippet": null
    }
  ]
}
```

---

### 4.2 `GET /v1/sources` (Stage 1)

Returns sources + feed health snapshot (last fetched, status, error streak).

---

### 4.3 `GET /v1/feed` (Stage 2+ cluster feed)

This is the public feed once StoryClusters exist (Stage 2). Fields that require Stage 3+ enrichment are present but nullable.

**Query**

* `tab=latest|trending|for_you` (`for_you` is Stage 5+)
* `topic_id=...` optional
* `content_type=...` optional
* `page=...`

**Response example**

```json
{
  "tab": "trending",
  "page": 1,
  "results": [
    {
      "cluster_id": "33333333-3333-3333-3333-333333333333",
      "canonical_title": "Researchers propose a faster way to train small language models",
      "distinct_source_count": 6,
      "content_type_badges": ["preprint", "news"],
      "method_badges": [],
      "updated_at": "2026-01-28T08:12:00Z",

      "takeaway": null,
      "confidence_band": null,
      "anti_hype_flags": [],

      "top_topics": [
        {"topic_id": "44444444-4444-4444-4444-444444444444", "name": "AI", "score": 0.91}
      ]
    }
  ]
}
```

---

### 4.4 `GET /v1/clusters/{id}` (Stage 2+; enriched in Stage 3+)

If a cluster has been merged, the API returns a redirect response pointing to the canonical cluster ID (see `design_docs/openapi.v0.yaml`).

**Response example**

```json
{
  "cluster_id": "33333333-3333-3333-3333-333333333333",
  "canonical_title": "BERT-style models get compressed without large accuracy loss",
  "created_at": "2026-01-27T18:00:00Z",
  "updated_at": "2026-01-28T08:12:00Z",
  "distinct_source_count": 5,
  "topics": [
    {"topic_id": "55555555-5555-5555-5555-555555555555", "name": "NLP", "score": 0.88}
  ],
  "content_type_breakdown": {
    "peer_reviewed": 0,
    "preprint": 1,
    "press_release": 0,
    "news": 4,
    "report": 0
  },
  "evidence": {
    "preprint": [
      {
        "item_id": "66666666-6666-6666-6666-666666666666",
        "title": "ALBERT: A Lite BERT...",
        "source": {"source_id": "77777777-7777-7777-7777-777777777777", "name": "arXiv"},
        "published_at": "2026-01-27T18:00:00Z",
        "url": "https://..."
      }
    ],
    "news": [
      {
        "item_id": "88888888-8888-8888-8888-888888888888",
        "title": "Explainer: Why smaller language models matter",
        "source": {"source_id": "99999999-9999-9999-9999-999999999999", "name": "Example News"},
        "published_at": "2026-01-28T01:00:00Z",
        "url": "https://..."
      }
    ]
  },

  "takeaway": null,
  "summary_intuition": null,
  "summary_deep_dive": null,
  "confidence_band": null,
  "method_badges": [],
  "anti_hype_flags": []
}
```

---

### 4.5 `GET /v1/topics/{id}` (Stage 2+; lineage served separately in Stage 4)

```json
{
  "topic_id": "55555555-5555-5555-5555-555555555555",
  "name": "NLP",
  "description_short": "Techniques for computers to understand and generate human language.",
  "latest_clusters": [/* cluster cards */],
  "trending_clusters": [/* cluster cards */]
}
```

---

### 4.6 `GET /v1/search?q=...` (Stage 2+)

Return grouped results:

```json
{
  "query": "ALBERT vs BERT",
  "clusters": [/* cluster cards */],
  "topics": [/* topics */]
}
```

---

### 4.7 `GET /v1/clusters/{id}/updates` (Stage 4)

```json
{
  "cluster_id": "33333333-3333-3333-3333-333333333333",
  "updates": [
    {
      "created_at": "2026-01-28T08:12:00Z",
      "change_type": "refinement",
      "summary": "Updated the Deep Dive based on a new benchmark comparison.",
      "diff": {
        "previously": ["The tradeoffs were unclear in multilingual settings."],
        "now": ["A new benchmark comparison suggests weaker multilingual performance than initially implied."],
        "because": ["A new comparison article discusses multilingual tradeoffs."]
      },
      "supporting_item_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
    }
  ]
}
```

---

### 4.8 `GET /v1/topics/{id}/lineage` (Stage 4)

```json
{
  "topic_id": "55555555-5555-5555-5555-555555555555",
  "nodes": [
    {"node_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "title": "BERT", "node_type": "model", "external_url": "https://..."},
    {"node_id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "title": "ALBERT", "node_type": "model", "external_url": "https://..."}
  ],
  "edges": [
    {
      "from": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "to": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "relation_type": "compresses",
      "evidence_item_ids": ["66666666-6666-6666-6666-666666666666"],
      "notes_short": "Parameter sharing + factorized embeddings reduce size."
    }
  ]
}
```

---

### 4.9 `GET /v1/glossary?term=...` (Stage 3)

```json
{
  "entry": {
    "glossary_entry_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "term": "Transformer",
    "definition_short": "A neural network architecture that uses attention to model sequences."
  }
}
```

---

### 4.10 `POST /v1/events` (Stage 5+)

```json
{
  "event_type": "save",
  "cluster_id": "33333333-3333-3333-3333-333333333333"
}
```

---

### 4.11 `POST /v1/feedback` (Stage 8)

```json
{
  "feedback_type": "confusing",
  "cluster_id": "33333333-3333-3333-3333-333333333333",
  "message": "The takeaway is unclear about whether this result was peer reviewed."
}
```

---

### 4.12 Admin endpoints (Stage 1+)

Admin endpoints are protected (v0 recommendation: `X-Admin-Token`) and defined in `design_docs/openapi.v0.yaml`:

* `POST /v1/admin/source_pack/import` (idempotent upsert of sources/feeds; format: `design_docs/source_pack_v0.md`)
* `PATCH /v1/admin/sources/{id}`
* `PATCH /v1/admin/feeds/{id}`
* `POST /v1/admin/ingestion/run`
* Stage 8 governance:
  * `GET /v1/admin/feedback`, `PATCH /v1/admin/feedback/{id}`
  * `POST /v1/admin/clusters/{id}/merge`
  * `POST /v1/admin/clusters/{id}/split`
  * `POST /v1/admin/clusters/{id}/quarantine`
  * `POST /v1/admin/clusters/{id}/unquarantine`
  * `PATCH /v1/admin/clusters/{id}`, `PUT /v1/admin/clusters/{id}/topics`
  * `POST /v1/admin/topics`, `PATCH /v1/admin/topics/{id}`, `POST /v1/admin/topics/{id}/merge`
  * `POST /v1/admin/lineage/nodes`, `POST /v1/admin/lineage/edges`
* Stage 10 ecosystem:
  * `POST /v1/admin/entities`, `PATCH /v1/admin/entities/{id}`, `POST /v1/admin/entities/{id}/merge`
  * `PUT /v1/admin/clusters/{id}/entities`
  * `POST /v1/admin/experiments`, `PATCH /v1/admin/experiments/{id}`
  * `PUT /v1/admin/feature_flags/{key}`

---

## 5) v0 heuristics (so you can implement without ML first)

### 5.1 Clustering similarity v0

Use a two-pass approach:

**Candidate selection**

* only consider clusters updated within last 14 days (configurable)
* compare against clusters sharing at least one:

  * keyword overlap (normalized tokens)
  * same preprint/paper ID (arXiv ID)
  * same entity/model term (BERT, ALBERT)

**Similarity score components (v0)**

* `title_sim` (token Jaccard or cosine on TF-IDF)
* `entity_overlap` (count)
* `time_proximity` (decay)
* `source_pattern_bonus` (syndication detection)

**Decision**

* if score ≥ threshold → assign to that cluster
* else create new cluster
* log “why” for debugging

### 5.2 Trending score v0

A simple, explainable formula:

* `velocity = new_items_last_6h + 0.5*new_items_last_24h`
* `diversity = distinct_source_types + distinct_sources`
* `recency_decay = exp(-hours_since_update / 24)`
* `trending = (velocity * 1.0 + diversity * 0.3) * recency_decay`

### 5.3 Topic tagging v0

* curated keyword rules + aliases
* source-based mapping (e.g., if Source is “NASA” → Space topic boost)
* store score; don’t over-tag (cap top topics per cluster)

### 5.4 Trust box v0

Compute breakdown from cluster items:

* count by content_type
* diversity score:

  * number of distinct sources
  * number of distinct source types

### 5.5 Confidence band v0

* **Early** if: mostly preprints/press releases OR single-source coverage OR anti-hype flags present
* **Growing** if: multiple independent sources + consistent reporting + some follow-up evidence
* **Established** if: authoritative reports / repeated evidence over long period / consensus docs

### 5.6 Anti-hype flags v0

Rule-based detection from snippet/abstract/press release text:

* “mice”, “rat”, “in vitro” → animal/preclinical indicator
* “N=” patterns → sample size extraction
* “first ever”, “breakthrough” → hype language flag (soft)
* preprint content type → always add `preprint_not_peer_reviewed`

### 5.7 Glossary linking v0

* maintain curated glossary list
* detect exact term matches + known variants
* cap tooltips shown per page to reduce clutter

### 5.8 Update diff v0

Compare last revision vs new revision and generate bullets:

* new sources added of a higher-trust type (peer-reviewed added)
* confidence band changed
* new limitations/assumptions added
* cluster merged/split (if implemented)

---

## 6) Quality gates (must-haves before showing enriched text)

### 6.1 Citation integrity rules

* Every explanation must attach supporting item IDs.
* If there is not enough accessible content to support a claim:

  * omit the claim
  * show “insufficient detail to summarize reliably” fallback.

### 6.2 Non-hallucination rules

* Don’t infer results not stated in sources.
* For preprints: don’t state conclusions as settled.

### 6.3 Guardrails for sensitive domains (esp. health)

* No prescriptive “you should” or medical advice tone.
* Emphasize uncertainty and evidence type.
* Always link to primary sources.

---

## 7) Observability (what to measure from day one)

**Ingestion**

* fetch success rate by source/feed
* average time from publish → ingested
* error streak alerts

**Clustering**

* % of items that attach to existing clusters
* oversized cluster alert (likely over-merged)
* cluster merge rate

**Enrichment**

* % clusters with takeaway + intuition + deep dive
* fallback rate (insufficient info)
* citation coverage rate

**User behavior**

* CTR on feed cards
* saves/hides ratio
* follow topic adoption
* notification open rate (later)

---

## 8) Security + privacy defaults

* Minimal personally identifying data
* Event logging opt-out (later)
* Rate limiting on API endpoints
* Admin endpoints protected

---

# What we do next (to finish Stage 0 cleanly)

If you’re happy with these docs, the only remaining Stage 0 work is to turn them into **“implementation checklists”** for Stage 1:

* Initial curated source list + feed URLs
* DB migration plan (tables + indexes)
* Ingestion worker schedule plan
* Minimal web UI routes and components
* “Definition of Done” for Stage 1
