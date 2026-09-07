# Curious Now

Curious Now is a calm, continuously updated science feed. It collects research,
science journalism, and frontier-lab publications; groups duplicate coverage into
canonical stories; and explains each story at the depth the reader wants.

The v2 product has three independent reading depths under a reader-facing title:

```text
Idea -> Explain -> Technical
```

- **Idea** gives a newcomer the intuition in a short paragraph.
- **Explain** gives a fuller intuitive account.
- **Technical** gives a technical but intuitive summary of the contribution.

Each layer is generated directly from the retrieved source text and records its
evidence-packet and prompt version. Technical works receive an intuitive display
title from the completed Idea; news keeps its original headline, and every source
title remains visible. Metadata and snippets alone are not treated as articles.

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

- a versioned registry spanning primary research, journalism, institutions,
  and public agencies;
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
