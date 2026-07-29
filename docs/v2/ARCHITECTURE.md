# Curious Now v2 — Architecture

## Design goals

The architecture optimizes for:

- one excellent web reader;
- continuous but asynchronous collection;
- precomputed, cacheable explanations;
- evidence provenance;
- failure isolation;
- very low idle cost;
- simple operation by one person.

It does not optimize for hypothetical clients, large editorial teams, or
high-volume user mutations.

## Runtime shape

V2 separates the read path from the write path.

```text
                         WRITE PATH (scheduled)
sources -> ingest -> normalize -> hydrate -> cluster -> evidence packet
                                                   -> conceptual spine
                                                   -> presentations -> concepts -> rank
                                                                        |
                                                                        v
                                                                     Postgres
                                                                        ^
                                                                        |
                         READ PATH (on demand)                          |
browser -> Next.js server components / route handlers ------------------+
```

### Reader

The Next.js application owns the public read path. Server-side code reads Postgres
directly and returns rendered pages or narrow route-handler responses.

There is no standalone public FastAPI deployment in the initial v2 architecture.
This removes an always-on service, cross-origin configuration, an extra network
hop, and a duplicated API type contract. A public API can be introduced if a
second real client appears.

### Pipeline

Python owns scheduled and operator-triggered work:

- source ingestion;
- document extraction;
- clustering;
- scholarly metadata enrichment;
- evidence-packet construction;
- conceptual-spine construction;
- display-title and explanation generation;
- concept candidate generation;
- ranking;
- maintenance and evaluation.

Pipeline jobs are idempotent. They may be run by GitHub Actions, a low-cost cron
service, or a local machine without changing their semantics.

### Storage

Postgres stores product records, provenance, generated explanations, and graph
relationships.

Object storage may hold legally permitted extraction artifacts that do not belong
in Postgres. A database record stores the object reference, checksum, access
policy, and provenance.

Redis is not part of v2. HTTP caching, server-rendering caches, and indexed
Postgres queries are sufficient until observed load demonstrates otherwise.

## Core pipeline

### 1. Ingest

- Fetch only configured feeds and APIs.
- Preserve source identity and source policy.
- Normalize URLs deterministically.
- Deduplicate exact items by canonical URL hash.
- Extract DOI, arXiv, PMID, and provider-native identifiers.
- Store metadata even when richer text is unavailable.

### 2. Hydrate

- Prefer abstracts and open-access primary text.
- Do not store paywalled full text.
- Store the extraction method, license/access class, checksum, and object
  reference.
- Extraction failure does not block the item or its story.

Abstracts come from the arXiv API for arXiv identifiers and Crossref for other
DOIs. Identifier types are selected in separate pools so a large single-source
ingestion cannot starve the other provider. Hydration only ever raises an item's
access class to what was actually fetched. Many DOIs — news and editorial items
in particular — publish no abstract at all; those are recorded as attempted and
retried later rather than refetched on every run.

Open-access full text is not yet extracted, so no story currently reaches the
`open_full_text` sufficiency that Technical requires.

### 3. Cluster

Clustering uses a confidence ladder:

1. exact scholarly identifier;
2. canonical URL identity;
3. strong bibliographic match;
4. conservative title/entity/time similarity;
5. otherwise create a separate story.

False merges are more harmful than temporary duplicate stories. Fuzzy decisions
must record a score and reason.

### 4. Construct the evidence packet

The evidence packet is the factual interface between retrieval and generation.
It contains structured claims, supporting items, excerpts or locators,
limitations, uncertainty, and prerequisite concepts.

Claims without supporting items are invalid. The evidence packet is versioned;
new evidence creates a new version rather than silently changing the basis of an
existing explanation.

### 5. Present

Every generated presentation references one evidence-packet version and one
conceptual spine.

- The display title is a versioned reader artifact, distinct from immutable source
  titles and the internal story working title.
- Title and Glance are generated for the broadest set of supported stories.
- Glance assumes no topic familiarity and establishes the simplest accurate
  intuition.
- Explain assumes foundational field familiarity and adds terminology, mechanism,
  evidence, comparison, and limitations.
- Technical is restricted to stories with suitable primary material and enough
  accessible text to inspect methods and evidence.
- Glance and Explain are orientation choices; Technical is a progressive
  investigation reached after either orientation.
- Generated content is never produced in a reader request.
- Model, prompt version, evidence-packet version, conceptual-spine version,
  generation status, and validation status are stored.

The normative content rules are defined in
[`PRESENTATION_CONTRACT.md`](PRESENTATION_CONTRACT.md). The screen hierarchy is
defined in [`READER_EXPERIENCE.md`](READER_EXPERIENCE.md).

### 6. Connect concepts and research

Bibliographic APIs provide citation and reference candidates. LLMs may propose
concept relationships but cannot publish unsupported research relationships.

Concept explanations are reusable, versioned assets. A concept is not regenerated
for every story that mentions it.

### 7. Rank

Ranking is computed in the pipeline and stores both a score and inspectable
reasons. Initial signals include:

- freshness;
- evidence quality;
- primary-source availability;
- independent-source diversity;
- estimated significance;
- topical variety;
- duplicate and low-information penalties.

Ranking does not use per-user engagement.

A weighted base score combines freshness, evidence quality, primary-material
availability, independent corroboration, and text sufficiency. A variety damper
then demotes each repeated principal source within a pass, so one bulk feed drop
cannot occupy the whole shelf. Every stored score records the reason for each
signal and any damping applied. Ranking is deterministic: the same stories and
clock produce the same order.

Source-level variety is the initial approximation of topical variety; a topic
signal replaces it once stories carry topic assignments. Significance and
duplicate penalties are not yet implemented.

## Publication rules

A story can be published when it has:

- a non-empty reader title chosen by the title fallback order in
  [`PRESENTATION_CONTRACT.md`](PRESENTATION_CONTRACT.md), which may be a validated
  display title or an attributed source-title fallback;
- at least one visible evidence item;
- a canonical source link;
- a validated presentation set for the layers its evidence supports.

Stories that never reach sufficient text stay `draft`: collected, clustered, and
available as evidence for stories that do publish, but never displayed. This
distinguishes two cases the reader must treat differently — a story that can
never be explained is withheld, while a published story whose newest enrichment
run failed or is still pending keeps showing its last valid explanations.

An explanation is eligible for display only when:

- its generation and validation succeeded;
- it references the newest evidence-packet version that has a complete validated
  presentation set — a newer packet version whose presentations are not yet
  validated does not withdraw the previous valid set;
- the packet contains no unsupported claims;
- its depth is appropriate for the available evidence.

Presentations from different evidence-packet versions must not be mixed in one
reader session.

## Failure model

- Source failure: retain prior content and record the feed error.
- Retrieval failure: keep the item as unpublished evidence and retry later; a
  story already published is unaffected.
- LLM failure: retain the previous valid explanation; withhold a story that has
  never had one.
- Display-title failure: use the safest eligible source title.
- Concept failure: omit the link; never block the story.
- Ranking failure: fall back to reverse chronological order.
- Read-store failure: show a clear temporary error; do not attempt generation.

## Deployment target

The initial low-cost target is:

- Next.js reader and thin server-side reads on a scale-to-zero platform;
- managed scale-to-zero Postgres;
- optional object storage;
- scheduled Python pipeline;
- batch LLM calls with persistent results.

The read application must remain usable while the pipeline is offline. Freshness
may degrade; availability must not.

## Transition strategy

V1 remains available under the `legacy-v0` tag. V2 is developed behind separate
Python modules and a fresh schema until it can serve a real feed.

Cutover occurs only after:

1. source import and ingestion work;
2. evidence-only stories appear in the reader;
3. generated display titles, Glance, and Explain are grounded in a versioned
   evidence packet and conceptual spine;
4. basic search and continuous pagination work;
5. a legacy-content importer has either been run or deliberately rejected.
