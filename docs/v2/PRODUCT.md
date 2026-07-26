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
2. Scroll through distinct science stories rather than duplicate links.
3. Read a short explanation of what happened and why it matters.
4. Change depth without changing the underlying facts.
5. Open a technical deep dive when the story is based on a suitable paper.
6. Tap an unfamiliar concept to learn it without losing the story.
7. Follow related concepts, papers, and developments through the knowledge web.

## Explanation depths

The UI uses reader-friendly names. `glance`, `explain`, and `technical` are the
canonical internal identifiers.

### Glance

- approximately 1–3 sentences;
- understandable in roughly ten seconds;
- states what happened and why it may matter;
- preserves uncertainty and important qualifications.

### Explain

- assumes curiosity but little topic-specific background;
- builds intuition before terminology;
- introduces only the prerequisites needed for this story;
- corresponds roughly to the original ELI5/ELI20 motivation, without infantilizing
  the reader.

### Technical

- only generated when accessible primary material is sufficient;
- explains the mechanism, method, evidence, assumptions, and limitations;
- includes an intuitive account, not merely a compressed paper;
- identifies prerequisites and links them to reusable concept cards.

The depths are alternate views of one evidence packet. They must not be generated
as independent interpretations of the source material.

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

Local browser preferences may remember display depth without introducing accounts.

## Success criteria

V2 succeeds when:

- opening the app reliably produces interesting, non-duplicate science stories;
- the Glance view is useful without opening the source;
- Explain creates genuine understanding for an unfamiliar topic;
- Technical helps a capable reader understand a paper without first reading it end
  to end;
- every generated claim remains inspectable against sources;
- concept links make an unfamiliar story easier rather than creating a distracting
  graph;
- a failed enrichment run results in stale or evidence-only content, never a broken
  reader;
- the system can operate at personal scale for negligible fixed infrastructure
  cost.
