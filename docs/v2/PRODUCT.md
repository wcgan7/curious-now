# Curious Now v2 — Product Contract

## Product promise

Curious Now is a calm, continuously updated feed of science worth understanding.
It collects research, science journalism, and frontier-lab publications; groups
coverage of the same development into one story; and explains that story at the
depth the reader wants.

> Scroll through science. Understand what happened. Go deeper when curiosity wins.

The product is a healthier use of spare attention, but it does not artificially
limit how far the reader can scroll. Collection is continuous and the feed is
effectively unbounded.

## Primary reader

The first reader is a curious technical generalist:

- knowledgeable in some domains and new to others;
- interested in both important research and well-reported science news;
- unwilling to read every source article or full paper;
- willing to go deep when an explanation builds the right prerequisites.

V2 is initially a single-reader/personal product. Multi-user behavior must not
shape the core architecture until the reading loop is proven.

## Core reader loop

1. Open a mobile-friendly feed.
2. Scroll through approachable titles for distinct science stories rather than
   duplicate links or inline summaries.
3. Open an interesting title into Glance, the default orientation for someone new
   to the topic.
4. Switch to Explain when already familiar with the field or when more context is
   wanted.
5. Enter Technical only after establishing the central intuition and deciding the
   work merits investigation.
6. Inspect original sources and supporting evidence from every presentation.
7. Tap an unfamiliar concept to learn it without losing the story.
8. Follow related concepts, papers, and developments through the knowledge web.

## Presentation ladder

Curious Now has four presentation layers, but they are not four equal tabs.

```text
Discovery                 Orientation                    Investigation

Title              ->     Glance and/or Explain    ->    Technical
                           new to it   know the field     go deep
```

`title` is a presentation layer, not an explanation depth. The canonical
explanation identifiers remain `glance`, `explain`, and `technical`.

### Title — discovery

- approximately 6–14 words;
- approachable without sacrificing the material qualification;
- describes the scientific development rather than merely naming the paper;
- accurate, specific, calm, and non-clickbait;
- sufficient for deciding whether to open the story.

Every source item retains its original title. A story may additionally have a
versioned display title derived from its current evidence packet. Generated titles
never overwrite source titles.

### Glance — orientation for a newcomer

Glance is the internal equivalent of ELI5, without using that label in the
interface.

- assumes no topic-specific knowledge;
- takes approximately 30–60 seconds to read;
- provides the simplest accurate intuition;
- states what happened, why it might matter, and the essential qualification;
- avoids jargon or explains it immediately;
- prefers a useful mental model over methodological detail.

Glance is the default presentation after opening a title.

### Explain — orientation for a familiar reader

Explain is the internal equivalent of ELI20.

- assumes foundational familiarity with the field;
- takes approximately 3–6 minutes to read;
- may use established terminology and useful jargon;
- explains what is new, how it works, how it differs from the normal approach,
  the key evidence, and the important limitations;
- remains intuitive rather than reproducing academic prose.

Explain must stand alone for a reader who skips Glance, while feeling like a
natural expansion for a reader who uses both.

### Technical — investigation

- is reached progressively from Glance or Explain rather than promoted as the
  normal entry point from the feed;
- takes approximately 8–15 minutes to read;
- is generated only when accessible primary material is sufficient;
- covers problem formulation, methods, experimental design, baselines, results,
  comparisons, assumptions, and limitations;
- uses equations or algorithms when they materially improve understanding;
- identifies prerequisites and links them to reusable concept cards;
- remains an intuitive walkthrough, not merely a compressed paper.

The interface encourages orientation before Technical but does not enforce reading
completion. Direct links to a Technical presentation remain valid.

### Cross-layer consistency

All four layers share one versioned evidence packet and one conceptual spine:

- central claim;
- genuine novelty;
- core intuition;
- why it matters;
- strongest supporting evidence;
- essential qualification;
- prerequisite concepts.

The presentations are adapted for different assumptions, not independently
invented interpretations. Glance is not produced by mechanically shortening
Explain, and Explain is not produced by truncating Technical.

The normative layer and evaluation rules live in
[`PRESENTATION_CONTRACT.md`](PRESENTATION_CONTRACT.md).

## The canonical story

A story is one scientific development, result, release, correction, or debate. It
may contain:

- a paper or preprint;
- a lab announcement;
- institutional or government material;
- independent journalism;
- later follow-up evidence.

Source items retain their identities and links. Clustering never turns several
sources into an unattributed synthetic article.

## Evidence and trust

Every published story must have at least one visible source. AI enrichment is
additive and must never be required for publication.

A story with limited accessible text is published in evidence-only mode. It may
show a title, source labels, available metadata, and links without generated
explanations.

Every generated factual claim must point to one or more supporting source items.
The application distinguishes:

- primary research;
- preprints;
- peer-reviewed work;
- lab or institutional announcements;
- press releases;
- government reports;
- independent journalism;
- discovery/referral sources.

Lab announcements and press releases are useful but are not independent
confirmation. Preprints are visibly labeled as not peer reviewed.

For medical and other high-risk claims, the product reports evidence and
uncertainty; it does not provide advice.

## Feed behavior

The feed:

- scrolls continuously through collected stories;
- presents one approachable display title per story with only minimal trust
  metadata;
- does not place Glance excerpts or equal depth controls inside the feed;
- opens a story into Glance by default;
- prioritizes freshness, significance, evidence quality, and topical variety;
- does not optimize for outrage, compulsion, or raw click-through rate;
- suppresses duplicates and low-information reposts;
- explains why exceptional stories are highlighted;
- keeps older stories reachable through scrolling, topics, concepts, and search.

Collection and enrichment are separate. V2 may collect every eligible item while
spending more inference on stories likely to provide reader value.

## Knowledge web

The knowledge web contains three explicit layers.

### Concepts

Examples: attention, query/key/value, residual connection, randomized controlled
trial, CRISPR, stellar spectroscopy.

Initial relationship types:

- `requires`
- `related_to`
- `part_of`
- `example_of`
- `contrasts_with`

### Research

Papers may:

- `cites`
- `extends`
- `replicates`
- `contradicts`
- `applies`

Bibliographic relationships should come from scholarly metadata when possible.
Interpretive relationships require provenance and reviewable evidence.

### Stories

Stories connect evidence items, papers, topics, and concepts. Updates remain part
of the story rather than becoming disconnected new posts.

## V2 scope

V2 includes:

- curated RSS/API ingestion;
- deterministic URL and paper-identifier normalization;
- paper metadata and legally accessible text hydration;
- story clustering;
- a structured evidence packet;
- a versioned conceptual spine and display title;
- Glance and Explain generation;
- Technical deep dives for suitable papers;
- visible evidence and trust information;
- topics and search;
- concept cards and prerequisite links;
- continuous feed ranking;
- pipeline observability sufficient for a single operator.

## Explicitly deferred

- accounts and authentication;
- follows, saves synced across devices, and personalization;
- notifications and email;
- experiments and feature-flag platforms;
- generic entity following;
- editorial workflow software beyond operator commands;
- Redis;
- engagement-event collection;
- vector search unless ordinary retrieval proves inadequate;
- native mobile applications;
- a public general-purpose API.

Local browser preferences may remember an orientation choice without introducing
accounts. Familiarity is topic-specific, so the product must not silently infer a
permanent expertise level from clicks.

## Success criteria

V2 succeeds when:

- opening the app reliably produces interesting, non-duplicate science stories;
- display titles are useful enough to scan without becoming sensational;
- a newcomer gains the right intuition from Glance;
- a field-aware reader gets meaningful detail from Explain without being forced
  through beginner material;
- moving from Glance to Explain feels like expansion rather than contradiction or
  repetition;
- Technical helps a capable reader understand a paper without first reading it end
  to end;
- Technical feels like a deliberate continuation of the established intuition;
- every generated claim remains inspectable against sources;
- concept links make an unfamiliar story easier rather than creating a distracting
  graph;
- a failed enrichment run results in stale or evidence-only content, never a broken
  reader;
- the system can operate at personal scale for negligible fixed infrastructure
  cost.
