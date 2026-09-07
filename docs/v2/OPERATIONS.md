# Curious Now v2 — Operations

## Local vertical slice

V2 uses a separate database and does not need Redis.

```bash
docker compose -f compose.v2.yaml up -d
export CURIOUS_NOW_V2_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/curious_now_v2

make v2-migrate
make v2-sync-sources
make v2-ingest

make reader-install
make reader-dev
```

The reader is then available at `http://localhost:3001`. It reads Postgres
directly. The ingestion process can be stopped without taking the reader down.
For development without exporting the URL in each shell, copy
`apps/reader/.env.example` to the ignored `apps/reader/.env.local` file.

Run the focused verification suite with:

```bash
make v2-check
make reader-build
```

The database integration test is opt-in:

```bash
export CURIOUS_NOW_V2_TEST_DATABASE_URL="$CURIOUS_NOW_V2_DATABASE_URL"
pytest tests/test_v2_db_ingestion.py
```

## Scheduled production shape

The low-fixed-cost deployment is deliberately two pieces:

1. a scale-to-zero Next.js reader connected to managed Postgres;
2. a scheduled Python command that runs `ingest-once`, followed later by
   hydration and enrichment commands.

There is no always-on Python API, worker process, Redis instance, or model call in
the request path.

One scheduler invocation runs a bounded, non-overlapping cycle:

```bash
.venv/bin/python scripts/v2_run_cycle.py --dry-run
.venv/bin/python scripts/v2_run_cycle.py
```

It collects due feeds, retrieves text, hydrates paper metadata, gates only stories
whose evidence changed, then spends the currently accrued part of the generation
budget. Each stage and the containing cycle record counters and bounded errors in
`pipeline_runs`. Individual feed failures use exponential backoff and do not roll
back successful feeds. A PostgreSQL advisory lock makes a second invocation exit
cleanly if the previous cycle is still running.

The checked-in user timer runs this command every 30 minutes on the current host:

```bash
systemctl --user link "$PWD/deploy/systemd/curious-now-v2-cycle.service"
systemctl --user link "$PWD/deploy/systemd/curious-now-v2-cycle.timer"
systemctl --user daemon-reload
systemctl --user enable --now curious-now-v2-cycle.timer

systemctl --user list-timers curious-now-v2-cycle.timer
journalctl --user -u curious-now-v2-cycle.service -n 100
```

The service reads `CURIOUS_NOW_V2_DATABASE_URL` from `.env.v2.example`, retrieves
at most 50 documents per invocation so a normal cycle fits inside its 30-minute
cadence, and gives a cycle 45 minutes before systemd considers it stuck. User
lingering must be enabled for the timer to keep running while the account is
logged out.

Feeds that expose an archive rather than a small rolling window set
`max_entries` in the source registry. Ingestion considers only that many entries
from the publisher-ordered head of the feed, so enabling a source cannot import
years of backlog on its first poll.

## Cost controls

- Collect feed metadata and snippets first for discovery, but do not publish or
  generate an article until an abstract or usable body has been retrieved.
- Resolve exact paper identifiers before spending inference on clustering.
- Publish source-backed stories before enrichment.
- Generate Idea broadly, Explain when the evidence contains a method or mechanism,
  and Technical only for open primary material. Each is one independent
  plain-text Luna call at low effort.
- Generate a short reader-facing title for papers, reports, and datasets from the
  completed Idea. Keep news and magazine source headlines unchanged; a failed
  title call falls back to the source title without blocking publication.
- Keep the evidence packet for provenance, routing, and ranking; do not turn it
  into a brief or checklist for the prose writer.
- Store every output by evidence-packet and prompt version; never regenerate on a
  page request.
- Pace model work against a constant `$20` UTC-day budget. At noon UTC, at most
  half has accrued; actual `generate` and title-backfill costs already recorded
  that day are subtracted before selecting another batch. Reserve `$0.15` per
  selected story and cap a cycle at 25 stories to limit overshoot when an
  individual response is unusually expensive.
- One-time title maintenance may use the remaining UTC-day headroom rather than
  only the currently accrued share. Its recorded `backfill_titles` cost is still
  included in the same `$20` ceiling, so normal generation pauses until pacing
  catches up.
- Reserve one third of each generated batch for journalism/news-like material and
  two thirds for technical material. Round-robin sources inside both lanes; if one
  lane has no backlog, let the other use the capacity.
- Reuse concept explanations across stories.
- Keep raw extraction artifacts in object storage only when permitted and useful.
- Measure actual query load before adding caches or search infrastructure.

## Operational invariants

- Production uses the fresh v2 schema only.
- The checked-in source registry is validated before it mutates the database.
- Sources removed from the registry become inactive rather than being deleted.
- A feed or model outage produces stale or evidence-only content.
- A migration runs once and is recorded in `schema_migrations`.
- The legacy schema is never written by v2.
- Ranking is not a scheduled stage: generation stores the stable presentation key
  needed by the reader, so repeatedly ranking unchanged stories would only create
  churn.
