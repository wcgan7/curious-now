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
                                                   -> direct depth summaries
                                                   -> concepts -> rank
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

Full text is resolved by trying every route an item offers, richest first:
arXiv LaTeXML HTML, PubMed Central JATS, the open-access copies OpenAlex knows
about, then the item's own page, with PDF last. Markup states its own sections,
figures, and tables; a PDF's have to be reconstructed from glyph geometry, so
every earlier option avoids that reconstruction.

Each candidate is fetched, extracted, and scored, and the richest result wins.
The walk stops early once a candidate is clearly good enough, so a paper whose
LaTeXML renders well never has its PDF pulled — a courtesy to the host as much
as a saving. Every attempt is recorded with its outcome, so an operator can see
why a source lost rather than only that it did.

Retrieval draws from every source in turn rather than in discovery order, since
a single large feed would otherwise fill batch after batch.

Abstracts come from the arXiv API for arXiv identifiers and Crossref for other
DOIs. Identifier types are selected in separate pools so a large single-source
ingestion cannot starve the other provider. Hydration only ever raises an item's
access class to what was actually fetched. Many DOIs — news and editorial items
in particular — publish no abstract at all; those are recorded as attempted and
retried later rather than refetched on every run.

The same responses carry the author list, which is stored verbatim per provider
rather than reconciled into a canonical person. arXiv gives one display string,
Crossref a given/family split and sometimes an ORCID; only the ORCID identifies
rather than describes, so it is the only field a later join should trust. Author
capture is deliberately not gated on the abstract — an entry whose summary is
unusable still named who wrote it. Affiliation is read where present and is
almost always absent, so where an author works remains a question for OpenAlex
and not one this stage can answer.

Open-access primary full text enables Technical. Abstracts can support Idea and,
when they state a method, Explain. Metadata and snippets are skipped.

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

The packet provides the method signal used to route Explain and records whether
the source is substantive enough to publish. It is a control-plane record for
provenance, classification, routing, and ranking; reader-facing prose is not
assembled from its fields.

Claims without supporting items are invalid. The evidence packet is versioned;
new evidence creates a new version rather than silently changing the basis of an
existing explanation.

### 5. Present

Every generated layer references one evidence-packet version.

- The source title is used unless a separate valid display title exists.
- Papers, reports, and datasets generate that display title from their completed
  Idea; reader-written news and magazine headlines remain unchanged.
- Idea is generated for every substantive article and assumes no topic familiarity.
- Explain is generated when the evidence carries a method or mechanism, and for
  open primary works.
- Technical is generated only from open primary material.
- Each depth is an independent plain-text Luna call over the retrieved source.
- The paper title is one independent plain-text Luna call over the completed Idea.
- A deeper failure does not block a new story's successful Idea, but an
  incomplete regeneration cannot replace the existing current set.
- An ineligible depth is not a failure; completeness is relative to the depths
  the selected source can support.
- Metadata and snippets do not enter generation.
- Generation disables both Codex shell implementations, runs from an empty
  working directory, ignores local instructions, and rejects any call in which
  the agent attempts to use another tool.
- Generated content is never produced in a reader request.
- Model, prompt version, evidence-packet version, usage, and status are stored.

The normative content rules are defined in
[`PRESENTATION_CONTRACT.md`](PRESENTATION_CONTRACT.md). The screen hierarchy is
defined in [`READER_EXPERIENCE.md`](READER_EXPERIENCE.md).

### 6. Connect concepts and research

Bibliographic APIs provide citation and reference candidates. LLMs may propose
concept relationships but cannot publish unsupported research relationships.

Concept explanations are reusable, versioned assets. A concept is not regenerated
for every story that mentions it.

### 7. Rank

Ranking stores a stable `effective_at` sort key and inspectable reasons from
validated presentation completion, categorical significance and publication
time. It does not use per-user engagement. See [`RANKING.md`](RANKING.md) for
the measured signal choices and the time-shift derivation.

Feed composition is deliberately separate from story quality. The reader
queries technical and accessible stories as independently ranked lanes,
interleaves them two-to-one, and spreads principal sources within each selected
page batch. Each lane has its own keyset cursor. This keeps a bulk paper feed
from filling the shelf without permanently lowering any individual story's
stored score or losing rows at a pagination boundary.

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

### Faults that do not raise

Most of this pipeline's real faults have been silent: text that parsed into
nonsense, a qualification written to a field nothing rendered, a book review
labelled peer reviewed. Nothing errored, and each was found by a later consumer
rather than by the stage that produced it. The checks against that are audits
over stored data, not assertions in the code path:

| Script | Asks |
| --- | --- |
| `v2_extraction_audit.py` | do the extractors still satisfy their invariants on frozen fixtures |
| `v2_corpus_audit.py` | is the text actually stored sound, and does each path's shape match its peers |
| `v2_source_audit.py` | does any source claim more than it can support, and is its feed mixed |

`v2_source_audit.py` MUST be run when a source is added. A feed's
`default_content_type` describes the feed, and a publisher that sends several
kinds of item down one URL makes that default wrong for most of what arrives —
which decides a review-status badge, a ranking weight, and whether the item is
resolved through open-access routes or only its own page.

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
3. direct Idea and Explain summaries are grounded in retrieved source text and
   reference a versioned evidence packet;
4. basic search and continuous pagination work;
5. a legacy-content importer has either been run or deliberately rejected.

### Legacy content: deliberately rejected

No importer will be written. V1's content stays in v1, and v2 carries only what
it collects itself.

Three reasons. Imported items would arrive with no retrieved full text, no
section structure, and no evidence packet, so the publication gate would hold
every one of them as a draft; making them publishable would mean running v2
retrieval across the lot, which is the same work as ingesting fresh material on
staler news. V1's generated explanations predate this contract — they reference
no evidence-packet version and no conceptual spine, and none of their claims are
grounded at claim level — so they could not be displayed as they stand, and
regenerating them costs what generating new stories costs. And volume was never
the problem: one ingestion run collected 1,998 stories, of which 72% of those
retrieved clear the gate.

Source configuration is the exception worth carrying over: feed quirks and
manual corrections v1 learned are cheap to port and touch no schema.

V1 remains readable under the `legacy-v0` tag if anything is ever needed from
it.
