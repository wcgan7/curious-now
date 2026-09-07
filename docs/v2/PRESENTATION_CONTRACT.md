# Curious Now v2 — Presentation Contract

## Purpose

One retrieved science source may produce three independent reader-facing views:

```text
Idea -> Explain -> Technical
```

They are choices of reading depth, not a document assembled in stages. Each view
MUST stand alone and MUST be generated directly from the retrieved source text.

## Source sufficiency

Metadata and snippets are not articles. A story whose best available material is
`metadata_only` or `snippet` MUST be skipped and MUST NOT enter generation.

An abstract or accessible article can support Idea. Explain additionally needs a
method or mechanism in the evidence, except that an open primary work is presumed
to contain enough material for an intuitive summary. Technical requires open
primary material: a paper, preprint, technical report, dataset, or equivalent
primary documentation rather than secondary coverage.

| Best available source | Idea | Explain | Technical |
| --- | --- | --- | --- |
| Metadata or snippet | No | No | No |
| Simple news, release, or announcement | Yes | No | No |
| Secondary source with a supported mechanism | Yes | Yes | No |
| Primary abstract with a supported method | Yes | Yes | No |
| Open primary work | Yes | Yes | Yes |

Technical eligibility MUST NOT depend on Explain being generated successfully.
A failure at one depth MUST NOT invalidate a successful depth.

## Generation objectives

The objectives below are the complete editorial instructions for the prose. They
are sent as plain-text requests, followed by the source title and retrieved source
text.

### Idea

```text
Please summarise the intuition behind this in a short paragraph suitable for reader without related knowledge:
```

Idea is the feed-level orientation for a newcomer. It uses the database depth
value `glance` for compatibility.

### Explain

For a paper:

```text
Please summarise the intuition behind this paper:
```

`paper` is replaced by `article`, `report`, or `dataset` when appropriate.

### Technical

For a paper:

```text
Please provide a technical but intuitive summary for this paper so a technical reader can get the key contribution essence without having to read the paper:
```

The document noun is replaced when appropriate. Technical is a substantial
self-contained summary, not a schema-shaped reconstruction of the paper.

## Model invocation

Reader-facing writing uses `gpt-5.6-luna` at low reasoning effort. Each depth is
an independent plain-text completion. Generation MUST NOT feed a writer:

- an editorial brief;
- a conceptual spine;
- an earlier reading depth;
- a semantic checklist;
- another model's critique;
- a requested word or sentence count beyond the natural wording of the prompt.

The title is a separate fourth completion for papers and technical reports. It
uses the completed Idea rather than rereading the source, so title writing does
not alter or intermediate the three reading depths.

The evidence packet remains a control-plane record for provenance, classification,
depth routing, and ranking. It MUST NOT become an intermediate representation from
which the prose is assembled.

## Validation

Production validation is mechanical. A layer is valid when:

- its model call completed;
- its response is nonempty;
- its text is safe to store.

The runtime MUST NOT reject prose for word count, sentence count, number of ideas,
heading choice, sentence overlap, centrality, readability, or whether a second
model agrees with it. There are no automatic semantic judges or rewrite passes.

Markdown headings MAY be parsed into display sections after generation. This is a
presentation convenience, not a validity requirement. The unmodified stored prose
remains the source of truth, and a response without headings remains valid.

## Titles

News, magazine, blog, and release headlines remain the reader title. Papers,
reports, and datasets receive a display title from their successful Idea using:

```text
Please rewrite this paper’s title as a short, intuitive and accurate title so a curious reader without related knowledge can immediately understand what it found, explained, or made possible, and return only the new title:

Original title: {source_title}

Intuitive title: {idea}
```

The original title always remains attached to its source item. If the title call
fails, the existing source/working-title fallback applies; failure or absence of
editorial title generation MUST NOT block a story.

## Storage and provenance

Each attempted layer records:

- story and evidence-packet IDs;
- depth;
- plain text and any mechanically derived display sections;
- status and failure reason;
- model provider and model name;
- prompt version;
- input and output token usage;
- creation and validation time.

All depths produced in one run reference the same evidence packet. The retained
conceptual-spine row is a schema-compatible batch identifier only; it does not
plan or constrain the direct prose.

## Publication

A successful Idea is sufficient to publish a new story; a deeper failure does
not invalidate it. Regeneration is stricter: an incomplete new attempt remains
recorded for diagnosis but does not replace the reader's existing current
version. If Idea fails and no current version exists, the story remains
unpublished even when a deeper call happened to complete.

No placeholder explanation is shown for an ineligible or failed depth. The source
link remains available for every published story.

## Evaluation

Subjective quality belongs in an offline prompt evaluation set, not the production
request path. Prompt changes SHOULD be reviewed against a small cross-field corpus
including primary research, medicine, physical science, climate science, and
method-heavy machine learning. Production does not ask a model to grade every
answer generated by another model.
