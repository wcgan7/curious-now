# Stage 2 — StoryClusters (Dedup + Trending + Search v1 + Topic Pages v1)

Stage 2 upgrades Stage 1’s “list of Items” into the canonical product unit: the **StoryCluster** (one story, many sources). This is the stage where the app stops feeling like an RSS reader and starts feeling like an organized system.

Stage numbering and next-stages references follow `design_docs/implementation_plan_overview.md`.

---

## 1) Scope

### 1.1 In scope (Stage 2)

**User-facing**

* Cluster-based feed with **Latest** and **Trending** tabs
* **StoryCluster page v0**: canonical title + evidence list (grouped by content type)
* **Topic pages v1**: topic → list of clusters (latest; trending optional)
* **Search v1**: cluster-first keyword search (topics optional)

**Backend**

* Exact dedupe + near-dup clustering into StoryClusters
* Cluster metrics (source diversity, velocity windows, trending score)
* Topic tagging v0/v1 (rules + aliases + source/category mapping)
* Postgres full-text search for clusters (good enough early)
* Admin/debug/observability for clustering (assignment logs, quarantine switches, quality metrics)

### 1.2 Out of scope (explicitly not Stage 2)

* **Stage 3:** understanding layer (takeaway/intuition/deep dive) + trust/uncertainty UI + glossary + method badges + anti-hype
* **Stage 4:** update tracking (“what changed”) + lineage timelines/graph
* **Stage 5:** accounts + personalization (follow topics, block sources, saves)
* **Stage 6:** notifications + digests
* **Stage 7:** mobile app (or PWA) + scaling/performance upgrades
* **Stage 8:** governance + editorial tooling
* **Stage 9:** platform hardening + search/ranking upgrades
* **Stage 10:** mature ecosystem (polish + extensibility)

---

## 2) Stage 2 entry criteria (hard blockers)

Stage 2 quality is dominated by Stage 1 data quality. Do not start Stage 2 until these are true:

1. **Stable ingestion**
   * Worker runs on schedule (prod or “always-on” dev)
   * ≥10 sources reliably update
   * Failed feeds are visible (error streak + last status + last fetched)
2. **Idempotency + canonicalization**
   * Re-running ingestion does not create duplicate Items
   * Canonical URL normalization is consistent enough that the same story is not split across multiple URLs
3. **Minimal data quality**
   * Most Items have `title`, `canonical_url`, and `published_at`
   * Missing/invalid `published_at` is tracked (and rare)
4. **Operational control**
   * You can disable a feed without redeploying
   * You can inspect recent ingestion output by source/feed (even a basic admin view)
5. **DB decision made**
   * Use Postgres `UUID` everywhere (locked in `design_docs/decisions.md`)

Strongly recommended (not blocking, but saves time):

* Keep some raw payload retention (even just raw feed entry JSON) for debugging clustering mistakes.
* Have at least **2–4 weeks** of Items to tune thresholds and trending.

---

## 3) UX requirements (Stage 2)

### 3.1 Cluster feed

**Latest** sorts by `story_clusters.updated_at DESC` (or `created_at` early).

**Trending** sorts by `story_clusters.trending_score DESC` (computed; see §6).

**Cluster card (v0)**

* canonical title
* content-type badges (aggregate: preprint / peer-reviewed / press release / news / report)
* `distinct_source_count` (“Covered by 6 sources”)
* “Updated X ago”
* top topics (1–3 chips)

Acceptance criteria:

* The feed feels **less spammy** than Stage 1 (syndicated reposts collapse).
* A user can get an overview of coverage diversity at a glance (source count + content types).

### 3.2 StoryCluster page v0 (coverage list)

This page is intentionally a **coverage + evidence** page in Stage 2 (no LLM summaries yet).

Required sections:

* canonical title
* metadata: updated time, source counts, top topics
* evidence list grouped by Item `content_type`:
  * `peer_reviewed`, `preprint`, `news`, `press_release`, `report`

Each evidence row shows:

* title
* source name
* published time
* “Read original” link

Acceptance criteria:

* Every cluster page has at least **1 evidence link**.
* Content-type grouping is consistent (driven by Item labels, not heuristics).

### 3.3 Topic pages v1

* Topic name (+ short description optional)
* Latest clusters in topic
* (Optional) Trending clusters in topic

Constraints:

* Cap topic tags per cluster (1–3, max 5).
* Avoid “topic soup”: topics must feel stable and meaningful.

### 3.4 Search v1 (cluster-first)

* Search returns clusters first; topics second (optional).
* Results should not show obvious duplicates (cluster-level result is canonical).

---

## 4) Data model changes (Postgres, UUID)

Assumptions:

* Stage 1 already has: `sources`, `source_feeds`, `items`
* Primary keys are `UUID` (`pgcrypto` + `gen_random_uuid()`)

Stage 2 adds:

* `story_clusters`
* `cluster_items`
* `topics`
* `cluster_topics`
* `cluster_search_docs`
* `cluster_assignment_logs` (debug)
* External IDs on `items` (arXiv/DOI/PMID)

### 4.1 SQL migrations (exact)

These are ready to apply as-is (assumes Stage 1 uses UUIDs; see `design_docs/decisions.md`).

Concrete migration files live under `design_docs/migrations/`:

* `design_docs/migrations/2026_01_29_0201_stage2_clusters.sql`
* `design_docs/migrations/2026_01_29_0202_stage2_topics.sql`
* `design_docs/migrations/2026_01_29_0203_stage2_search.sql`
* `design_docs/migrations/2026_02_03_0204_stage2_cluster_redirects.sql` (safe merges; stable cluster URLs)

#### 4.1.1 `2026_01_29_0201_stage2_clusters.sql`

```sql
-- 2026_01_29_0201_stage2_clusters.sql
-- Stage 2: StoryClusters + ClusterItems + optional debug logs + external IDs on items.

BEGIN;

-- UUID generator (Postgres)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- (Optional) Enums for clarity and consistency
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_status') THEN
    CREATE TYPE cluster_status AS ENUM ('active', 'merged', 'quarantined');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cluster_item_role') THEN
    CREATE TYPE cluster_item_role AS ENUM ('primary', 'supporting', 'background');
  END IF;
END$$;

-- Add external ID columns to items (recommended for clustering quality)
ALTER TABLE items
  ADD COLUMN IF NOT EXISTS arxiv_id TEXT,
  ADD COLUMN IF NOT EXISTS doi TEXT,
  ADD COLUMN IF NOT EXISTS pmid TEXT,
  ADD COLUMN IF NOT EXISTS external_ids JSONB;

CREATE INDEX IF NOT EXISTS idx_items_arxiv_id ON items (arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_doi ON items (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_pmid ON items (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_external_ids_gin ON items USING GIN (external_ids);

-- StoryClusters table
CREATE TABLE IF NOT EXISTS story_clusters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status cluster_status NOT NULL DEFAULT 'active',

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  canonical_title TEXT NOT NULL,
  representative_item_id UUID NULL REFERENCES items(id) ON DELETE SET NULL,

  distinct_source_count INT NOT NULL DEFAULT 0,
  distinct_source_type_count INT NOT NULL DEFAULT 0,
  item_count INT NOT NULL DEFAULT 0,

  velocity_6h INT NOT NULL DEFAULT 0,
  velocity_24h INT NOT NULL DEFAULT 0,

  trending_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  recency_score DOUBLE PRECISION NOT NULL DEFAULT 0,

  metrics_extra JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_story_clusters_updated_at ON story_clusters (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_clusters_trending_score ON story_clusters (trending_score DESC);

-- ClusterItems join table
CREATE TABLE IF NOT EXISTS cluster_items (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,

  role cluster_item_role NOT NULL DEFAULT 'supporting',
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (cluster_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_items_item_id ON cluster_items (item_id);
CREATE INDEX IF NOT EXISTS idx_cluster_items_cluster_added_at ON cluster_items (cluster_id, added_at DESC);

-- (Strongly recommended) assignment logs for debugging clustering decisions
CREATE TABLE IF NOT EXISTS cluster_assignment_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  decided_cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,

  decision TEXT NOT NULL CHECK (decision IN ('created_new', 'attached_existing', 'merged_clusters')),

  candidate_cluster_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
  threshold_used DOUBLE PRECISION NULL
);

CREATE INDEX IF NOT EXISTS idx_cluster_assignment_logs_created_at ON cluster_assignment_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_assignment_logs_item_id ON cluster_assignment_logs (item_id);

COMMIT;
```

#### 4.1.2 `2026_01_29_0202_stage2_topics.sql`

```sql
-- 2026_01_29_0202_stage2_topics.sql
-- Stage 2: Topics + ClusterTopics.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  description_short TEXT NULL,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  parent_topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topics_aliases_gin ON topics USING GIN (aliases);

CREATE TABLE IF NOT EXISTS cluster_topics (
  cluster_id UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,

  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (cluster_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_topics_topic_cluster ON cluster_topics (topic_id, cluster_id);

COMMIT;
```

#### 4.1.3 `2026_01_29_0203_stage2_search.sql`

```sql
-- 2026_01_29_0203_stage2_search.sql
-- Stage 2: Search v1 (cluster-first) using Postgres full-text search.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS cluster_search_docs (
  cluster_id UUID PRIMARY KEY REFERENCES story_clusters(id) ON DELETE CASCADE,

  -- worker-controlled text blob:
  -- canonical title + top N item titles + optional identifiers (arxiv_id/doi)
  search_text TEXT NOT NULL DEFAULT '',

  -- generated tsvector for fast full-text search
  search_tsv TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(search_text, ''))
  ) STORED,

  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cluster_search_docs_tsv ON cluster_search_docs USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS idx_cluster_search_docs_updated_at ON cluster_search_docs (updated_at DESC);

COMMIT;
```

---

## 5) Clustering + dedup heuristics (v0, explainable)

Design goals:

* **Explainable** and tunable (config-driven thresholds)
* **Conservative** against over-merging (bad merges destroy trust)
* **Improved by external IDs** (arXiv/DOI/PMID)

### 5.1 Inputs

From Stage 1 Items:

* `canonical_url` / `canonical_hash` (exact dedupe key)
* `title` (+ normalized tokens)
* `published_at` (time proximity)
* `source_id` (diversity bonus, same-source penalties)
* `content_type` (used for UI grouping; optional weighting)
* external IDs when available: `arxiv_id`, `doi`, `pmid`

### 5.2 Text normalization + tokenization (v0)

Normalize:

* lowercase
* replace hyphens with spaces
* strip punctuation
* collapse whitespace

Tokenize:

* split on non-alphanumeric
* keep tokens length ≥ 3
* remove stopwords
* optionally keep a small allow-list of important short tokens (`ai`, `ml`, `jwst`, `bert`, …)

### 5.3 External ID extraction (arXiv + DOI)

arXiv (new style):

* `\\b\\d{4}\\.\\d{4,5}(v\\d+)?\\b`

arXiv (old style):

* `\\b[a-z\\-]+\\/\\d{7}(v\\d+)?\\b`

DOI (case-insensitive):

* `\\b10\\.\\d{4,9}\\/[-._;()\\/:A-Z0-9]+\\b`

Rule:

* If a new Item matches an existing cluster by arXiv/DOI/PMID → **attach with certainty** (no fuzzy scoring).

### 5.4 Candidate selection (avoid comparing against every cluster)

When a new Item arrives:

1. **Hard candidates by external IDs**
   * If `item.arxiv_id` exists: find clusters containing any Item with that `arxiv_id`
   * Same for DOI/PMID
2. **Text candidates by full-text search**
   * Build a `plainto_tsquery` from title tokens and query `cluster_search_docs.search_tsv`
   * Restrict to clusters updated within the last `timeWindowDays` (default 14)
   * Limit to `maxCandidates` (default 200)

### 5.5 Similarity scoring (v0)

If no external ID match:

Compute:

* `tokens_item` = token set from item title
* `tokens_cluster` = token set from cluster canonical title (or search_text tokens)
* `jaccard = |∩| / |∪|`
* `overlap = |∩|`
* `timeProx = exp(-daysDiff / timeDecayDays)`

Score:

```
baseScore =
  w_title * jaccard +
  w_time  * timeProx +
  w_ovl   * min(overlap / 6, 1)
```

Bonuses:

* `+ newSourceBonus` if the new Item’s source is not already represented in the cluster

Anti-overmerge guards:

* reject if `overlap < minTokenOverlap`
* reject if `jaccard < minTitleJaccard`
* if only one overlapping token and `singleTokenGuard` enabled → reject

Decision:

* attach to best cluster if `score >= attachScore`
* otherwise create a new cluster

### 5.6 Default config (`config/clustering.v0.json`)

```json
{
  "timeWindowDays": 14,
  "maxCandidates": 200,

  "thresholds": {
    "attachScore": 0.72,
    "highConfidenceAttachScore": 0.82,
    "minTokenOverlap": 2,
    "minTitleJaccard": 0.42,
    "singleTokenGuard": true
  },

  "scoringWeights": {
    "titleJaccard": 0.65,
    "timeProximity": 0.25,
    "tokenOverlap": 0.10
  },

  "bonuses": {
    "newSourceBonus": 0.04,
    "externalIdMatchArxiv": 1.0,
    "externalIdMatchDoi": 0.95
  },

  "timeDecayDays": 7,

  "stopwords": [
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "its", "new", "of", "on", "or", "that",
    "the", "this", "to", "via", "with", "study", "researchers", "report"
  ],

  "rareTokenMinLength": 3
}
```

### 5.7 Canonical title selection (v0)

After attaching an Item:

* prefer titles that are descriptive and human-readable (e.g., 30–160 chars)
* avoid ALL CAPS and spam patterns
* optionally prefer titles from higher-reliability sources (if you maintain tiers)
* if a preprint/paper is present, the paper title is often the best canonical title

Update:

* `story_clusters.canonical_title`
* `story_clusters.representative_item_id`
* `cluster_search_docs.search_text` (see next section)

### 5.8 Search-doc maintenance (required in Stage 2)

Maintain `cluster_search_docs.search_text` whenever:

* cluster canonical title changes, or
* a new Item is attached

Recommended `search_text` composition:

* canonical title
* + top N (e.g., 8) most recent Item titles
* + external IDs (arXiv/DOI) if present

### 5.9 Safety valves (Stage 2 must-have)

* **Oversized cluster alert:** if a cluster grows beyond N Items within 24h, flag for review (often over-merge or syndication storm).
* **Cluster quarantine:** allow setting `story_clusters.status = 'quarantined'` so new Items cannot attach until reviewed.
* **Decision logging:** write `cluster_assignment_logs` for every assignment (or at least for low-confidence decisions).

---

## 5.10 Sanity test cases (must-link / cannot-link)

Use these as quick manual checks while tuning thresholds.

Must-link (should cluster together):

1. External ID match (arXiv):
   * “ALBERT: A Lite BERT…” (arXiv `1909.11942`)
   * “New preprint 1909.11942 introduces ALBERT…”
2. Near-duplicate news phrasing:
   * “NASA announces Artemis II crew…”
   * “Artemis II mission crew revealed by NASA”
3. Press release syndication:
   * “University scientists develop new battery cathode…”
   * “New fast-charging cathode material discovered…”

Cannot-link (should NOT cluster together):

1. Single-token collision:
   * “BERT compression improves training efficiency…”
   * “BERT used for protein sequence classification…”
2. Generic overlap only:
   * “Study reveals new mechanism in cell signaling”
   * “Study reveals new mechanism in galaxy formation”

---

## 6) Trending spec v0 (cluster-level)

Trending should be explainable and stable.

Signals:

* `velocity_6h`: Items added to cluster in last 6 hours
* `velocity_24h`: Items added to cluster in last 24 hours
* `distinct_source_count`: number of distinct sources in cluster
* `recency_decay`: based on hours since cluster updated

Example formula:

* `velocity = velocity_6h + 0.5 * velocity_24h`
* `diversity = min(distinct_source_count, 10)`
* `recency_decay = exp(-hours_since_update / 24)`
* `trending_score = (velocity * 1.0 + diversity * 0.3) * recency_decay`

Storage:

* write to `story_clusters.trending_score`
* optionally also store `story_clusters.recency_score` (to debug)

---

## 7) Topic tagging v0/v1

Start with ~15–30 top-level topics (Space, Biology, AI, Climate, Medicine, Physics…).

Each topic has:

* `name`
* optional `description_short`
* `aliases` (JSON array; e.g., “NLP” aliases include “natural language processing”, “LLM”, …)

Tagging approach (Stage 2):

* keyword matching over cluster canonical title + top evidence titles
* source-based boosts (e.g., NASA → Space)
* preprint category mapping (e.g., arXiv subject feeds → topics)

Output constraints:

* cap topics per cluster to 1–3 (max 5)
* store per-topic confidence as `cluster_topics.score`

---

## 8) Search v1 (cluster-first)

Implement cluster search via Postgres full-text search over `cluster_search_docs.search_tsv`.

Return format (v0):

* clusters: title, updated_at, distinct_source_count, top topics
* topics (optional): name + id

---

## 9) API changes (Stage 2)

Stage 2 introduces cluster-first endpoints while preserving the Stage 1 Item feed for debugging.

Recommended endpoints:

* `GET /v1/feed?tab=latest|trending&topic_id=&page=`
  * returns StoryCluster cards
* `GET /v1/clusters/{id}`
  * returns cluster metadata + evidence list grouped by content type
* `GET /v1/topics`
  * returns topic list
* `GET /v1/topics/{id}`
  * returns topic metadata + cluster list (latest; trending optional)
* `GET /v1/search?q=...`
  * returns clusters (primary) + topics (secondary, optional)

Debug/internal:

* `GET /v1/items/feed` (Stage 1 behavior; Items ordered by published_at)

---

## 10) Worker jobs & backfills (Stage 2)

Stage 2 introduces at least one new processing job beyond ingestion.

### 10.1 Job: cluster assignment

Trigger:

* on new Item insert/update, or
* scheduled batches (safer early; avoids per-insert hotspots)

Steps:

1. extract external IDs from the Item (arXiv/DOI/PMID)
2. find candidate clusters (IDs, then FTS)
3. score candidates and decide attach/create
4. upsert `story_clusters`, `cluster_items`
5. update `cluster_search_docs`
6. write `cluster_assignment_logs`

Must be:

* idempotent (reruns don’t reshuffle clusters unpredictably)
* debuggable (logs have enough context to explain decisions)

### 10.2 Job: backfill clustering (needed at Stage 2 start)

* Take the most recent N days/weeks of Items and cluster them in order (by `published_at`)
* After backfill, cluster feed should be non-empty and duplicates should collapse

### 10.3 Job: trending metrics computation

Trigger:

* every 10 minutes, or
* recompute on cluster changes + periodic “reconciliation” job

Compute:

* `velocity_6h`, `velocity_24h`, `distinct_source_count`, `trending_score`

### 10.4 Job: topic tagging

* compute `cluster_topics` for clusters (initial backfill + incremental updates)

---

## 11) Admin + debugging tooling (Stage 2)

Must-have:

* Cluster inspect page (view evidence list + source counts + topics)
* Ability to **quarantine** a cluster (`status = quarantined`) to stop further attachments
* View recent `cluster_assignment_logs` (why did it attach?)

Strongly recommended:

* CLI/admin scripts for safe manual merge/split
  * (UI can come later; a safe script prevents emergencies from blocking progress)
* “Re-run clustering for last X hours/days” backfill tool

### 11.1 Merge behavior (locked to avoid broken links)

Merging clusters must preserve stable IDs for URLs/bookmarks:

* When merging **A → B**:
  * move (or re-home) `cluster_items` from A into B
  * set `story_clusters.status = 'merged'` for A
  * insert `cluster_redirects(from_cluster_id = A, to_cluster_id = B)`
* API behavior for `GET /v1/clusters/{id}`:
  * if the requested cluster is `merged`, return a redirect response pointing to the target cluster (details in `design_docs/openapi.v0.yaml`)

Splitting is handled without redirects in v0:

* A split is “extract some items into a new cluster”, while the original cluster remains `active` and keeps its ID.

---

## 12) Observability + quality gates (Stage 2)

Track (at minimum):

* assignment rate: % of Items attaching vs creating new clusters
* cluster size distribution (alert on very large clusters)
* quarantine rate (signals model drift or noisy sources)
* trending feed churn (too jumpy = unstable score)

Quality gates:

* must/cannot-link constraints should pass on a golden set (see §13)
* investigate if over-merge spikes after config changes

---

## 13) Clustering QA harness (golden set + test runner)

Goal: catch regressions (over-merges and under-merges) when tuning thresholds.

Suggested structure:

```
/qa/clustering/
  items.json
  expected_clusters.json
  must_cannot_pairs.json
  run_eval.ts
```

Sample dataset files (synthetic but realistic enough to catch common failures):

### `qa/clustering/items.json`

```json
[
  {
    "id": "itm_a1",
    "source": "arxiv",
    "url": "https://example.org/arxiv/1909.11942",
    "title": "ALBERT: A Lite BERT for Self-Supervised Learning of Language Representations",
    "published_at": "2026-01-10T09:00:00Z",
    "content_type": "preprint",
    "arxiv_id": "1909.11942"
  },
  {
    "id": "itm_a2",
    "source": "science_news",
    "url": "https://example.org/news/albert-lite-bert",
    "title": "Preprint 1909.11942 proposes ALBERT, a smaller BERT-style language model",
    "published_at": "2026-01-10T12:00:00Z",
    "content_type": "news",
    "arxiv_id": "1909.11942"
  },
  {
    "id": "itm_a3",
    "source": "mit_news",
    "url": "https://example.org/mit/albert-compression",
    "title": "A parameter-sharing trick shrinks BERT-like models without major accuracy loss",
    "published_at": "2026-01-11T08:00:00Z",
    "content_type": "press_release"
  },

  {
    "id": "itm_b1",
    "source": "nasa",
    "url": "https://example.org/nasa/artemis-ii-crew",
    "title": "NASA announces Artemis II crew for a lunar flyby mission",
    "published_at": "2026-01-15T14:00:00Z",
    "content_type": "press_release"
  },
  {
    "id": "itm_b2",
    "source": "space_news",
    "url": "https://example.org/spacenews/artemis-ii-crew",
    "title": "Artemis II crew revealed as NASA prepares for the next Moon flyby",
    "published_at": "2026-01-15T16:00:00Z",
    "content_type": "news"
  },
  {
    "id": "itm_b3",
    "source": "esa_blog",
    "url": "https://example.org/esa/artemis-overview",
    "title": "What Artemis II means for future lunar exploration",
    "published_at": "2026-01-16T09:00:00Z",
    "content_type": "news"
  },

  {
    "id": "itm_d1",
    "source": "polar_research",
    "url": "https://example.org/polar/microplastics-antarctic-snow",
    "title": "Microplastics detected in Antarctic snow samples, study reports",
    "published_at": "2026-01-20T09:00:00Z",
    "content_type": "news"
  },
  {
    "id": "itm_d2",
    "source": "environment_news",
    "url": "https://example.org/env/microplastics-antarctica",
    "title": "Researchers find microplastics in Antarctic snowfall",
    "published_at": "2026-01-20T11:00:00Z",
    "content_type": "news"
  },
  {
    "id": "itm_d3",
    "source": "ngo_report",
    "url": "https://example.org/report/plastics-south-pole",
    "title": "Briefing: pathways of plastic pollution reaching polar regions",
    "published_at": "2026-01-21T07:00:00Z",
    "content_type": "report"
  },

  {
    "id": "itm_x1",
    "source": "ml_blog",
    "url": "https://example.org/ml/bert-protein",
    "title": "BERT-style models can classify protein sequences more accurately",
    "published_at": "2026-01-12T10:00:00Z",
    "content_type": "news"
  },
  {
    "id": "itm_x2",
    "source": "ml_news",
    "url": "https://example.org/ml/bert-compression-speed",
    "title": "BERT compression improves training efficiency for language models",
    "published_at": "2026-01-11T10:00:00Z",
    "content_type": "news"
  }
]
```

### `qa/clustering/expected_clusters.json`

```json
{
  "clusters": {
    "CL_ALBERT": ["itm_a1", "itm_a2", "itm_a3"],
    "CL_ARTEMIS_II": ["itm_b1", "itm_b2", "itm_b3"],
    "CL_MICROPLASTICS_ANTARCTICA": ["itm_d1", "itm_d2", "itm_d3"],
    "CL_BERT_PROTEIN": ["itm_x1"],
    "CL_BERT_COMPRESSION": ["itm_x2"]
  }
}
```

### `qa/clustering/must_cannot_pairs.json`

```json
{
  "must_link": [
    ["itm_a1", "itm_a2"],
    ["itm_b1", "itm_b2"],
    ["itm_d1", "itm_d2"]
  ],
  "cannot_link": [
    ["itm_x1", "itm_x2"],
    ["itm_a1", "itm_b1"]
  ]
}
```

### 13.1 Pairwise quality metric

* Use **pairwise F1** over all item pairs in the golden set.
* Add hard constraints via must-link / cannot-link pairs.

### 13.2 Sample `qa/clustering/run_eval.ts`

This assumes you have a `clusterItems(items, config)` function that returns `Map<Item.id, predictedClusterId>`.

```ts
import fs from "node:fs";
import path from "node:path";

type Item = {
  id: string;
  title: string;
  published_at: string;
  content_type: string;
  source: string;
  url: string;
  arxiv_id?: string;
  doi?: string;
};

type Config = any;

function loadJson<T>(p: string): T {
  return JSON.parse(fs.readFileSync(p, "utf8")) as T;
}

function clusterItems(_items: Item[], _config: Config): Map<string, string> {
  // Implement with Stage 2 heuristics.
  throw new Error("clusterItems not implemented");
}

function buildExpectedLabelMap(expected: { clusters: Record<string, string[]> }): Map<string, string> {
  const m = new Map<string, string>();
  for (const [label, ids] of Object.entries(expected.clusters)) {
    for (const id of ids) m.set(id, label);
  }
  return m;
}

function evaluatePairwise(expected: Map<string, string>, predicted: Map<string, string>, ids: string[]) {
  let tp = 0, fp = 0, fn = 0, tn = 0;

  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const a = ids[i], b = ids[j];
      const expSame = expected.get(a) === expected.get(b);
      const predSame = predicted.get(a) === predicted.get(b);

      if (expSame && predSame) tp++;
      else if (!expSame && predSame) fp++;
      else if (expSame && !predSame) fn++;
      else tn++;
    }
  }

  const precision = tp + fp === 0 ? 1 : tp / (tp + fp);
  const recall = tp + fn === 0 ? 1 : tp / (tp + fn);
  const f1 = (precision + recall) === 0 ? 0 : (2 * precision * recall) / (precision + recall);

  return { tp, fp, fn, tn, precision, recall, f1 };
}

function checkMustCannot(
  pairs: { must_link: [string, string][], cannot_link: [string, string][] },
  predicted: Map<string, string>
) {
  const failures: string[] = [];

  for (const [a, b] of pairs.must_link) {
    if (predicted.get(a) !== predicted.get(b)) failures.push(`MUST-LINK FAILED: ${a} and ${b} should be in same cluster.`);
  }

  for (const [a, b] of pairs.cannot_link) {
    if (predicted.get(a) === predicted.get(b)) failures.push(`CANNOT-LINK FAILED: ${a} and ${b} should NOT be in same cluster.`);
  }

  return failures;
}

function main() {
  const root = path.resolve(process.cwd(), "qa/clustering");
  const items = loadJson<Item[]>(path.join(root, "items.json"));
  const expectedClusters = loadJson<{ clusters: Record<string, string[]> }>(path.join(root, "expected_clusters.json"));
  const pairs = loadJson<{ must_link: [string, string][], cannot_link: [string, string][] }>(path.join(root, "must_cannot_pairs.json"));
  const config = loadJson<Config>(path.resolve(process.cwd(), "config/clustering.v0.json"));

  const expectedLabelMap = buildExpectedLabelMap(expectedClusters);
  const ids = items.map(i => i.id);

  const predicted = clusterItems(items, config);
  const stats = evaluatePairwise(expectedLabelMap, predicted, ids);
  const failures = checkMustCannot(pairs, predicted);

  console.log("=== Pairwise Clustering Eval ===");
  console.log(stats);
  console.log("\\n=== Must/Cannot Pair Checks ===");
  if (failures.length === 0) console.log("All must-link / cannot-link checks passed.");
  else failures.forEach(f => console.log(f));

  // Suggested gates (tune as you iterate)
  const minF1 = 0.90;
  const maxFailures = 0;

  if (stats.f1 < minF1 || failures.length > maxFailures) {
    console.error("\\n❌ Clustering regression detected.");
    process.exit(1);
  } else {
    console.log("\\n✅ Clustering quality gate passed.");
  }
}

main();
```

---

## 14) Execution plan (Stage 2 milestones)

* **ST2-A — Schema**
  * apply migrations; seed initial topics; add minimal admin views
* **ST2-B — Backfill**
  * backfill last N days of Items into clusters; validate with spot checks
* **ST2-C — Incremental clustering**
  * “on new item” clustering job + assignment logs + quarantine support
* **ST2-D — Trending**
  * compute/store velocities + trending score; add Trending tab in UI
* **ST2-E — Topics**
  * tagging job + topic pages
* **ST2-F — Search**
  * maintain `cluster_search_docs`; `/v1/search` endpoint; UI
* **ST2-G — Quality**
  * metrics dashboards + QA harness wired into CI
* **ST2-H (optional) — Manual merge/split tools**
  * safe CLI/scripts (admin UI later)

---

## 15) Stage 3 readiness (resolved defaults)

Stage 3 (“understanding layer”) attaches to clusters. Before moving on:

* Stage 3 explanations live as **nullable columns on `story_clusters`**, with per-section `*_supporting_item_ids` for citations (see `design_docs/decisions.md`).
* Text policy is **metadata-first** (no paywalled full text). Summaries are generated only when sufficient accessible primary text exists; otherwise fall back to evidence-only (see `design_docs/decisions.md`).
* Label rules are enforced via `items.content_type` (preprint disclaimer, press release warnings, etc.).
