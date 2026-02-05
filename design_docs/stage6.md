# Stage 6 — Notifications + Digests (High-signal return loops)

Stage 6 brings users back **usefully** (not addictively) using the “meaningful change” rules locked in `design_docs/decisions.md`. It ships two notification primitives:

1. **Story update alerts** (when a watched StoryCluster meaningfully changes)
2. **Topic digests** (daily/weekly summaries for followed topics)

Stage numbering follows `design_docs/implementation_plan_overview.md`. API contract source of truth: `design_docs/openapi.v0.yaml`.

---

## 1) Scope

### 1.1 In scope (Stage 6)

**User-facing**

* “Watch this story” on a StoryCluster page (email updates)
* Topic digests (daily/weekly) for followed topics
* Notification settings: on/off, frequency, quiet hours, timezone

**Backend**

* Notification job queue + delivery logs (email-first)
* Scheduler jobs to enqueue:
  * story update alerts (from Stage 4 update logs)
  * topic digests (from clusters in followed topics)
* Rate limiting + dedupe (no spam)
* Templates: concise email content that links back to the cluster/topic pages

### 1.2 Out of scope (explicitly not Stage 6)

* Push notifications (mobile) (Stage 7+)
* ML recommender-driven notification targeting (keep it rules-based)
* “Trending alerts” (optional later; not shipped by default in Stage 6 v0)

---

## 2) Entry criteria (prereqs)

Stage 6 assumes:

1. Stage 5 accounts exist (users + sessions + prefs)
2. Stage 4 update tracking exists:
   * `update_log_entries` emitted only for meaningful changes (per `design_docs/decisions.md`)
3. Stage 2+ topics and clusters exist (`topics`, `cluster_topics`, `story_clusters`)

---

## 3) Resolved defaults (no blockers)

To avoid “we must decide X” blockers, Stage 6 v0 defaults are locked here:

1. **Channel (v0):** email only.
2. **Opt-in:** email notifications are **off by default**; user enables in Settings.
3. **Timezone:** default `UTC` until user sets one (IANA string, e.g. `America/Los_Angeles`).
4. **Quiet hours default:** `22:00–08:00` (local to the user’s timezone).
5. **Digest default:** weekly digest (Monday 08:00 local) when enabled.
6. **Story watch alerts:** send as soon as possible outside quiet hours, deduped per update log entry.
7. **Daily rate limit:** max **5** story-update emails per user per day; overflow rolls into the next digest.

---

## 4) Data model (Stage 6)

Concrete SQL migration: `design_docs/migrations/2026_02_03_0500_stage6_notifications_digests.sql`.

### 4.1 Tables

**`user_cluster_watches`**

* join table: which StoryClusters a user is watching (for update alerts)

**`notification_jobs`**

* durable job queue + delivery record for notifications
* includes:
  * `dedupe_key` (unique) to prevent duplicates
  * `scheduled_for` for quiet-hours deferral
  * `payload` (json) describing what to send (cluster id, update_log_entry id, topic ids, etc.)

---

## 5) API additions (Stage 6)

Stage 6 adds “watch story” endpoints (session-auth required):

* `POST /v1/user/watches/clusters/{cluster_id}`
* `DELETE /v1/user/watches/clusters/{cluster_id}`
* `GET /v1/user/watches/clusters`

Notification settings are part of Stage 5 prefs:

* `GET /v1/user/prefs`
* `PATCH /v1/user/prefs`

---

## 6) Notification settings shape (v0)

Stored inside `user_prefs.notification_settings` (jsonb). v0 shape:

```json
{
  "email": {
    "enabled": false,
    "topic_digest_frequency": "off",
    "story_update_alerts_enabled": false
  },
  "timezone": "UTC",
  "quiet_hours": { "start": "22:00", "end": "08:00" },
  "limits": { "max_story_update_emails_per_day": 5 }
}
```

Allowed `topic_digest_frequency`: `off` | `daily` | `weekly`.

---

## 7) Jobs (Stage 6)

### 7.1 Job: enqueue story-update alerts (triggered by Stage 4 updates)

Trigger:

* on insert into `update_log_entries`, or
* periodic scan for new update log entries not yet notified

Steps:

1. For the cluster’s watchers (`user_cluster_watches`), check the user’s settings:
   * `email.enabled == true`
   * `email.story_update_alerts_enabled == true`
2. Create a `notification_jobs` row per user:
   * `notification_type = cluster_update`
   * `dedupe_key = "cluster_update:{user_id}:{update_log_entry_id}"`
   * `payload` includes: `cluster_id`, `update_log_entry_id`
   * `scheduled_for` respects quiet hours (if within quiet hours, schedule for quiet-end time)
3. Enforce per-user daily rate limit:
   * if limit exceeded, skip creating immediate jobs; rely on digest

### 7.2 Job: enqueue topic digests (scheduled)

Trigger: every 5–15 minutes (scheduler)

For each user with digests enabled and “due”:

1. Determine digest window:
   * daily: last 24h
   * weekly: last 7d
2. Build digest candidates:
   * clusters in followed topics (`user_topic_follows` → `cluster_topics`)
   * include clusters that:
     * are newly created, or
     * have meaningful updates (via `update_log_entries`)
3. Create a single `notification_jobs` row:
   * `notification_type = topic_digest`
   * `dedupe_key = "topic_digest:{user_id}:{period_key}"`
   * `payload` includes: `topic_ids`, `cluster_ids` (top N), `period_start`, `period_end`
   * `scheduled_for` defaults to 08:00 local time on the day it’s due (respects quiet hours)

### 7.3 Job: sender worker (email)

Trigger: continuous worker (poll due jobs)

Steps per job:

1. Load payload context from DB (cluster title, update summary, topics)
2. Render email (subject + html + text) with:
   * cluster/topic title(s)
   * short summary (use Stage 4 `update_log_entries.summary` when available)
   * link back to the app (cluster page)
3. Send via provider (v0 default: Postmark; if not configured, log emails in dev)
4. Mark job status:
   * `sent_at`, `status=sent` on success
   * `attempts += 1`, `status=error`, `last_error` on failure (retry with backoff)

---

## 8) Content rules (trust + anti-hype in notifications)

Hard rules:

* Never send an “update” email unless the change is meaningful (Stage 4 policy).
* Never imply certainty in subject lines for preprint-only clusters.
* If a cluster is evidence-only (no Stage 3 summaries), the email must fall back to:
  * canonical title + update summary + evidence links (no invented explanation).

---

## 9) Observability & quality gates (Stage 6)

Track:

* jobs queued/sent/failed by notification_type
* retries and failure reasons (provider errors, bad payloads)
* per-user email volume distribution (ensure no spam outliers)
* unsubscribe/disable rates (proxy for quality)

Quality gates:

* Deduping: no duplicate sends for the same `dedupe_key`
* Quiet hours: no sends inside the user’s quiet hours window (except explicit override)
* Rate limit: never exceed max story-update emails per user per day

---

## 10) Remaining blockers requiring your decision

None for the roadmap as written (Stage 6 defaults are resolved in §3).

