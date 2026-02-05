# Curious Now — Code Review Notes

This document tracks issues found during the review, with priorities and fix status.

Legend:
- **Priority**: Critical / High / Medium / Low
- **Status**: Open / Fixed

## Issues

| ID | Priority | Status | Area | Summary |
|---:|:--------:|:------:|------|---------|
| 1 | Critical | Fixed | `curious_now/migrations.py` | `python -m curious_now.cli migrate` crashed after first run when using `dict_row` (`KeyError: 0` from `row[0]`). |
| 2 | Critical | Fixed | `curious_now/repo_stage10.py` | Feature-flag upsert overwrote unspecified fields with defaults (e.g., omitting `enabled` disabled the flag; omitting `config` reset it). |
| 3 | High | Fixed | `curious_now/api/routes_stage5.py` | Magic-link tokens were printed to stdout by default (credential leakage risk). |
| 4 | High | Fixed | `curious_now/api/routes_stage5.py` | Session cookie was always set with `secure=False` (unsafe for HTTPS deployments). |
| 5 | High | Fixed | `curious_now/api/routes_stage2.py` | ETag + Redis cache versioning used second-granularity timestamps; multiple updates within a second could serve stale data for up to the cache TTL. |
| 6 | Medium | Fixed | `curious_now/api/deps.py` | Admin token comparison was not constant-time (`==` vs `secrets.compare_digest`). |
| 7 | Medium | Fixed | `curious_now/api/routes_stage2.py` | Feed cache key included `user_id` even for `latest/trending` tabs (unnecessary cache fragmentation). |
| 8 | Medium | Fixed | Patch endpoints | Patch handlers couldn’t clear nullable fields because they didn’t distinguish “field omitted” vs “field explicitly set to null/empty”. |
| 9 | Medium | Fixed | `curious_now/rate_limit.py` | Rate limiting used `request.client.host` only; behind proxies it may rate-limit the proxy IP, not the user. |
| 10 | Medium | Fixed | `curious_now/notifications.py` | `_parse_hhmm()` could raise `ValueError` for malformed user prefs (e.g. `"xx:yy"`), potentially breaking notification enqueue/send loops. |
| 11 | Low | Fixed | Repo hygiene | Local artifacts exist in-tree (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.venv`). Added `.gitignore` for common local artifacts. |
| 12 | Low | Open | Minor consistency | Some small duplication of helpers and minor polish opportunities remain. |
| 13 | Critical | Fixed | `curious_now/clustering.py` | Stage 2 clustering worker had runtime issues (undefined `conn` in scoring, incorrect `threshold_used` type for external-ID logs). |
| 14 | Medium | Fixed | `curious_now/ingestion.py` / `curious_now/clustering.py` | Old-style arXiv ID regex was incorrectly escaped, preventing extraction of `hep-th/0601001`-style IDs. |
| 15 | Medium | Fixed | Stage 2 config | Clustering config file referenced by the worker was missing (`config/clustering.v0.json`). |
| 16 | Medium | Fixed | Tests + Redis | With Redis enabled, cached `/v1/feed` responses could leak across tests (DB is truncated between tests but Redis isn’t). Tests now flush Redis per test run. |
