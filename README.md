# Curious Now

Curious Now is a calm, continuously updated science feed. It collects research,
science journalism, and frontier-lab publications; groups duplicate coverage into
canonical stories; and explains each story at the depth the reader wants.

The v2 product has a progressive four-layer presentation:

```text
Title -> Glance and/or Explain -> Technical
```

- **Title** supports fast, calm discovery in the feed.
- **Glance** gives a newcomer the simplest accurate intuition.
- **Explain** gives a field-aware reader the important terminology and detail.
- **Technical** investigates methods, evidence, results, and limitations.

All layers derive from one versioned evidence packet and conceptual spine. Every
published story keeps its original source titles visible, and stories can appear in
evidence-only mode when AI enrichment is unavailable.

## V2 status

V2 is an active clean-boundary rebuild on the `v2` branch. The previous
implementation is preserved by the `legacy-v0` Git tag and remains runnable during
the transition.

The v2 source of truth is:

- [Product contract](docs/v2/PRODUCT.md)
- [Presentation contract](docs/v2/PRESENTATION_CONTRACT.md)
- [Reader experience and wireframes](docs/v2/READER_EXPERIENCE.md)
- [Architecture](docs/v2/ARCHITECTURE.md)
- [Porting decisions](docs/v2/PORTING.md)
- [Operations and cost controls](docs/v2/OPERATIONS.md)

The first executable slice is in place:

- a versioned registry with 15 sources and 16 feeds;
- deterministic feed parsing, URL normalization, and identifier extraction;
- a fresh PostgreSQL schema and idempotent migration command;
- evidence-packet, explanation-depth, publication, and reader contracts;
- a fresh Next.js reader under `apps/reader/` with continuous cursor pagination.

Run the focused checks with:

```bash
make v2-check
```

Apply the fresh schema to an empty database with:

```bash
export CURIOUS_NOW_V2_DATABASE_URL=postgresql://...
make v2-migrate
```

## Intended runtime

```text
scheduled Python pipeline -> Postgres <- Next.js reader
```

The pipeline ingests, normalizes, clusters, constructs evidence packets, generates
explanations, links concepts, and ranks stories. The reader performs thin
server-side reads and never invokes an LLM during a page request.

Initial v2 deliberately excludes accounts, notifications, experiments, generic
entity infrastructure, Redis, engagement tracking, and a standalone public API.

## Repository transition

The existing v1 directories remain in place temporarily so behavior can be ported
with tests rather than rewritten from memory. New v2 Python code lives under
`curious_now_v2/`, the fresh schema lives under `db/v2/`, and focused v2 tests live
with the root test suite.

Do not extend the old stage-numbered architecture on the v2 branch.

## Legacy implementation

To inspect or run the former implementation:

```bash
git switch --detach legacy-v0
```

Return to v2 with:

```bash
git switch v2
```
