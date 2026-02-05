# Stage 5 — Accounts + Personalization (“For You”, Saves, Follows)

Stage 5 makes Curious Now feel “sticky” without turning it into a black-box feed. The goal is **user control** (follow topics, block sources, save stories) and a **transparent, simple recommender** for the “For You” tab.

Stage numbering follows `design_docs/implementation_plan_overview.md`. Locked cross-stage decisions remain in `design_docs/decisions.md`.

---

## 1) Scope

### 1.1 In scope (Stage 5)

**User-facing**

* Accounts (v0: email magic link)
* Follow topics
* Block sources (hide evidence items from blocked sources)
* Saves/bookmarks (reading list)
* Hide story (“not interested”)
* Reading mode default (Intuition-first vs Deep Dive-first)
* Personalized feed: `GET /v1/feed?tab=for_you` + neutral `latest`

**Backend**

* Auth/session tables + minimal auth endpoints
* User preference tables (normalized join tables, not blobs)
* Engagement event logging (for ranking + metrics)
* “For You” ranking v1 (rules-based, explainable)

### 1.2 Out of scope (explicitly not Stage 5)

* Notifications/digests (Stage 6)
* Complex ML recommenders (Stage 7+)
* Editorial tooling beyond simple safety controls (Stage 8)

---

## 2) Entry criteria (prereqs)

Stage 5 assumes:

1. Stage 2 cluster feed exists (`GET /v1/feed`)
2. Topic tagging exists (`topics` + `cluster_topics`)
3. Source list exists (`sources`) and is stable enough to block/mute reliably

Stage 3/4 are helpful but not required for Stage 5 (reading mode is a UI preference; it does not require new enrichment).

---

## 3) Product rules (resolved defaults; no blockers)

To avoid Stage 5 getting blocked on product decisions, v0 defaults are locked here:

1. **Auth method (v0):** email magic link + server-side session cookie (`cn_session`, httpOnly, secure in prod).
   * Email delivery default: Postmark in prod; if no provider token is configured, log the magic link in server logs (dev-friendly).
2. **For You requires auth:** `GET /v1/feed?tab=for_you` returns `401` if not authenticated.
3. **Blocks behavior:** blocking a source hides that source’s Items everywhere (feeds + cluster evidence list). A cluster remains visible if it still has ≥1 unblocked evidence Item.
4. **Saves behavior:** saving a cluster is binary (saved/not saved) and appears in a “Saved” list.
5. **Hide story behavior:** hides a cluster from all feeds for that user (until unhidden).
6. **Ranking transparency:** v0 ranking is rules-based and must be explainable (no opaque embeddings required).

---

## 4) Data model (Stage 5)

Concrete SQL migration: `design_docs/migrations/2026_02_03_0400_stage5_accounts_personalization.sql`.

### 4.1 Tables (v0)

* `users`
  * email identity (normalized) + timestamps
* `user_sessions`
  * session token hash + expiry + revoke
* `auth_magic_link_tokens`
  * one-time login tokens (hash + expiry + used_at)
* `user_prefs`
  * `reading_mode_default` + `notification_settings` (used in Stage 6 later)
* `user_topic_follows` (join)
* `user_source_blocks` (join)
* `user_cluster_saves` (join)
* `user_cluster_hides` (join)
* `engagement_events`
  * click/open/save/follow/block/hide events; `user_id` optional (allowed) but “For You” uses authed events

---

## 5) API additions (Stage 5)

Source of truth is `design_docs/openapi.v0.yaml`.

### 5.1 Auth (magic link)

* `POST /v1/auth/magic_link/start`
  * body: `{ "email": "user@example.com" }`
  * behavior: create user if needed; create a short-lived login token; send email (in dev: log link)
  * response: `{ "status": "sent" }`

* `POST /v1/auth/magic_link/verify`
  * body: `{ "token": "..." }`
  * behavior: verify token, create session, set `cn_session` cookie
  * response: `{ "user": { ... } }`

* `POST /v1/auth/logout`
  * behavior: revoke current session, clear cookie
  * response: `{ "status": "ok" }`

### 5.2 User prefs and state

* `GET /v1/user`
* `GET /v1/user/prefs`
* `PATCH /v1/user/prefs`

### 5.3 Follows / blocks / saves / hides

* `POST /v1/user/follows/topics/{topic_id}`
* `DELETE /v1/user/follows/topics/{topic_id}`
* `POST /v1/user/blocks/sources/{source_id}`
* `DELETE /v1/user/blocks/sources/{source_id}`
* `POST /v1/user/saves/{cluster_id}`
* `DELETE /v1/user/saves/{cluster_id}`
* `POST /v1/user/hides/{cluster_id}`
* `DELETE /v1/user/hides/{cluster_id}`
* `GET /v1/user/saves` (reading list)

### 5.4 Events

* `POST /v1/events`
  * accepts an event with optional foreign keys (cluster/item/topic)
  * used for metrics + ranking signals

---

## 6) “For You” recommender v1 (rules-based)

Goal: a feed a user can understand and control.

### 6.1 Candidate set

For an authenticated user:

1. Start from clusters in followed topics:
   * `user_topic_follows` → topic_ids
   * join `cluster_topics` → clusters in last `timeWindowDays` (default 14)
2. Add a small exploration slice (optional v0):
   * top trending clusters in those topics (even if slightly older)
3. Exclude:
   * clusters in `user_cluster_hides`
   * clusters with zero remaining evidence after filtering blocked sources (see §3.3)

### 6.2 Scoring (simple, explainable)

Compute a score per cluster:

* `topicMatchScore`: max topic score among the user’s followed topics (from `cluster_topics.score`)
* `recencyScore`: decay by `story_clusters.updated_at`
* `qualityBoost` (optional v0): boost if cluster has primary evidence (`peer_reviewed`/`preprint`/`report`)
* `engagementBoost`: boost if user recently saved/opened similar topic clusters (from `engagement_events`)

Example:

```
score =
  0.55 * topicMatchScore +
  0.35 * recencyScore +
  0.05 * qualityBoost +
  0.05 * engagementBoost
```

### 6.3 Diversity constraints (anti-bubble)

Apply simple caps:

* max N results per topic in first page (default 6)
* max M results from the same source type dominating (default 12/20)

### 6.4 Output

* `GET /v1/feed?tab=for_you` returns standard `ClusterCard`s.
* Recommended: include optional `why_in_feed` metadata on cluster cards (e.g., “Because you follow AI”) if the client wants it (see OpenAPI).

---

## 7) Observability & quality gates (Stage 5)

Track:

* auth success rate + token verify failures
* active users (weekly), saves per user, follow/unfollow rates
* “For You” CTR vs Latest CTR
* block rate by source (useful for source quality audits later)

Quality gates:

* For You must never return clusters the user explicitly hid.
* Blocking a source must remove its Items from evidence lists for that user.
* No personalized ranking logic is allowed to depend on paywalled full text (see `design_docs/decisions.md`).

---

## 8) Remaining blockers requiring your decision

None for the roadmap as written (Stage 5 defaults are resolved in §3).
