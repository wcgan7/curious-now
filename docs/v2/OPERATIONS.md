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

The reader is then available at `http://localhost:3000`. It reads Postgres
directly. The ingestion process can be stopped without taking the reader down.

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

One scheduler invocation can process a bounded number of due feeds:

```bash
curious-now-v2 ingest-once config/v2/sources.json --limit 25
```

Each run records counters and bounded error summaries in `pipeline_runs`.
Individual feed failures use exponential backoff and do not roll back successful
feeds.

## Cost controls

- Collect feed metadata and snippets first; this is inexpensive and immediately
  useful.
- Resolve exact paper identifiers before spending inference on clustering.
- Publish source-backed stories before enrichment.
- Generate Glance broadly, Explain selectively, and Technical only for accessible
  primary research.
- Store every output by evidence-packet and prompt version; never regenerate on a
  page request.
- Batch model work and cap it by stories, input characters, and estimated spend per
  run.
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
