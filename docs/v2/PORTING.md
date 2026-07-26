# Curious Now v2 — Porting Decisions

V2 ports behavior, not files. Existing code is copied only after its assumptions
are checked against the v2 product and accompanied by focused tests.

## Port with focused tests

| V1 area | V2 decision |
| --- | --- |
| URL normalization | Port deterministic rules and expand source-specific fixtures |
| DOI/arXiv extraction | Port corrected identifier handling |
| RSS/Atom ingestion | Port fetch/parse behavior behind a smaller interface |
| Paper extractors | Port open-access extraction and provenance behavior |
| Paywall safeguards | Port and strengthen |
| Exact-ID clustering | Port DOI/arXiv attachment behavior |
| Feed/source configuration | Convert to a v2 source registry with clearer roles |
| Retry/advisory-lock behavior | Reuse the operational pattern |
| Evidence UI components | Port selectively after the v2 read model exists |
| Extractor tests | Retain fixtures that describe real edge cases |

## Rewrite around v2 contracts

| V1 area | Reason |
| --- | --- |
| Fuzzy clustering | Needs inspectable decisions and false-merge evaluation |
| AI generation | Depths must derive from one evidence packet |
| Feed ranking | Must reflect the new significance/evidence contract |
| Story page | Trust and depth selection are the primary interface |
| Topic classification | Needs a smaller taxonomy and explicit confidence |
| Updates/lineage | Split concept, paper, and story relationships |
| Database access | Replace stage repositories with domain-oriented modules |
| CLI | Replace accumulated commands with a small operator surface |
| Frontend API types | Remove dependence on a hypothetical full-platform OpenAPI |

## Do not port into initial v2

- user accounts, sessions, preferences, follows, and saves;
- notification queues and email delivery;
- experiments and general feature flags;
- generic entity administration;
- engagement event collection;
- Redis caching and rate-limit administration;
- maintenance-mode and backup HTTP endpoints;
- offline-sync APIs;
- public semantic-search APIs;
- stage-numbered route and repository modules;
- the accumulated v1 migration chain;
- CLI-based LLM providers;
- the v1 ten-stage documentation as product authority.

## Source registry changes

V2 distinguishes source role from quality. A source can be:

- `primary_research`
- `journalism`
- `lab_announcement`
- `institutional`
- `government`
- `press_release`
- `discovery`

Reliability is not represented by a single universal tier. The system records
properties relevant to the claim being made: primary versus secondary,
peer-review state, independence, access policy, and source identity.

For example, a community link aggregator may be useful for discovery but must not
count as independent evidence.

## Data migration

V2 starts from a fresh schema. If legacy data is retained, a one-way importer will:

1. import sources and source policies;
2. import canonical items and paper identifiers;
3. recreate story membership conservatively;
4. import explanations only when supporting item IDs are intact;
5. exclude accounts, events, notifications, experiments, and cache state.

The importer is not a compatibility layer. V2 never writes to the v1 schema.
