# Curious Now — URL Normalization v0 (Canonicalization + Idempotency)

Stage 1 idempotency and Stage 2 clustering rely on a deterministic `normalized_canonical_url` and `canonical_hash = sha256(normalized_canonical_url)` (locked in `design_docs/decisions.md`).

This doc defines the exact v0 rules and a minimal “overrides” config format.

---

## 1) Deterministic normalization rules (apply in order)

Given an input URL `u`:

1. Parse with a standard URL parser.
2. Drop the fragment (`#...`).
3. Normalize scheme and host casing (`HTTPS://EXAMPLE.COM` → `https://example.com`).
4. Normalize default ports:
   * `:80` for `http`, `:443` for `https` → removed.
5. Normalize path:
   * collapse duplicate slashes
   * remove trailing slash **only** when path is not `/`
6. Normalize query parameters:
   * remove known tracking params (see §2)
   * sort remaining params by key then value
   * keep params that change content (do not blanket-drop all queries)
7. Return the resulting URL string.

Output must be identical across ingestion runs and across services (API/worker/admin).

---

## 2) Tracking params to drop (default set)

Drop these when present (case-insensitive key match):

* `utm_*`
* `gclid`
* `fbclid`
* `mc_cid`
* `mc_eid`
* `ref`
* `ref_src`
* `cmpid`
* `icid`
* `ocid`

Note: this list can grow over time, but changing it affects idempotency; treat edits as a migration-like change and document it.

---

## 3) Per-source overrides (optional, recommended)

Some sources publish multiple URL variants (AMP, mobile subdomains, etc.). v0 supports a small overrides file:

`config/url_normalization_overrides.v0.json`

```json
{
  "overrides": [
    {
      "match": { "host": "example.com" },
      "drop_query_params": ["src", "partner"],
      "rewrite_rules": [
        { "from_prefix": "https://example.com/amp/", "to_prefix": "https://example.com/" }
      ]
    }
  ]
}
```

### 3.1 Semantics

* `match.host`: exact host match (v0); apply the first matching override.
* `drop_query_params`: additional query keys to drop for that host.
* `rewrite_rules`: simple prefix rewrites applied after base normalization.

If no override matches, base normalization rules apply.

