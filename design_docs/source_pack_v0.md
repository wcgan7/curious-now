# Curious Now — Source Pack v0 (Seed Format)

Stage 1 requires a way to add/edit/disable sources and feeds **without code changes**. The v0 mechanism is a **Source Pack** JSON file that can be imported by:

* an idempotent CLI script (recommended), and/or
* the admin endpoint `POST /v1/admin/source_pack/import` (defined in `design_docs/openapi.v0.yaml`).

This doc defines the file format and the idempotent upsert rules.

---

## 1) File format (`source_pack.v0.json`)

Top-level shape:

```json
{
  "sources": [
    {
      "name": "NASA",
      "homepage_url": "https://www.nasa.gov/",
      "source_type": "government",
      "reliability_tier": "tier1",
      "active": true,
      "terms_notes": "RSS OK; metadata-first storage.",
      "feeds": [
        {
          "feed_url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
          "feed_type": "rss",
          "fetch_interval_minutes": 15,
          "active": true
        }
      ]
    }
  ]
}
```

### 1.1 Allowed enums

* `source_type`: `journalism` | `journal` | `preprint_server` | `university` | `government` | `lab` | `blog`
* `reliability_tier`: `tier1` | `tier2` | `tier3`
* `feed_type`: `rss` | `atom` | `api`

---

## 2) Idempotent upsert rules (must follow)

### 2.1 Sources

Upsert key: `sources.name` (unique constraint in DB).

* If a source exists by name: update its fields (including `active`).
* If it does not exist: insert it.

### 2.2 Feeds

Upsert key: `(source_id, feed_url)` (unique constraint in DB).

* If the feed exists for that source+URL: update `feed_type`, `fetch_interval_minutes`, `active`.
* If it does not exist: insert it.

### 2.3 Deletions (v0 policy)

Do not hard-delete sources/feeds via the source pack.

* “Remove” by setting `active: false`.

Why: avoids accidental data loss and keeps ingestion history (`feed_fetch_logs`) intact.

---

## 3) Recommendations (v0)

* Keep an initial pack with ≥10 sources across categories (journalism + preprints + institutions).
* Keep `terms_notes` short but specific (paywall, snippet allowance, ToS reminders).
* Prefer a conservative `fetch_interval_minutes` (15–60) to start.

