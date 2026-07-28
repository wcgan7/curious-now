# Curious Now v2 — Presentation Contract

## Purpose

This document defines how one evidence-backed story becomes four reader-facing
layers:

```text
Title -> Glance and/or Explain -> Technical
```

It is normative for generation, validation, storage, and reader behavior. `MUST`,
`SHOULD`, and `MAY` describe requirements in decreasing order of strength.

## Terminology

### Source title

The title supplied by a paper, publisher, lab, institution, or news source.

- It MUST be retained verbatim apart from safe text normalization.
- It MUST remain attached to its source item.
- It MUST remain visible in the source shelf.
- It MUST never be overwritten by generated editorial text.

### Working title

An internal label used while clustering and operating on a story. It may initially
be copied from a source title. It is not a guaranteed reader-facing artifact.

### Display title

The approachable title shown in the Curious Now feed and story header.

- It MUST describe the development represented by the story.
- A generated display title MUST reference one evidence-packet version.
- It MUST be versioned rather than silently rewritten.
- It MUST fall back safely when no generated title is valid.

### Evidence packet

The versioned set of supported claims, citations, limitations, uncertainty, and
text-sufficiency information that constrains every generated presentation.

### Conceptual spine

The shared semantic plan from which all four layers are rendered. It contains:

- the central supported claim;
- what is genuinely new;
- the simplest accurate intuition;
- why it may matter;
- the strongest supporting evidence;
- the essential qualification or uncertainty;
- prerequisite concepts;
- the source roles relevant to interpreting the claim.

Every factual element in the conceptual spine MUST resolve to one or more supported
claims in the evidence packet.

## Reader progression

The layers have different product roles.

| Layer | Stage | Familiarity assumption | Expected use |
| --- | --- | --- | --- |
| Title | Discovery | None | Decide whether to open |
| Glance | Orientation | New to the topic | Establish simple intuition |
| Explain | Orientation | Knows the foundations | Understand the important details |
| Technical | Investigation | Ready to inspect the work | Examine methods and evidence |

Glance and Explain are alternative orientation paths. A reader MAY use either or
both. Technical is a progressive deep dive after orientation, not the normal
entry point from the feed.

## Title contract

### Target

- Approximately 6–14 words and normally no more than 100 characters.
- One plain-language statement or noun phrase.
- Specific enough to distinguish the development from adjacent stories.

### Required behavior

A display title MUST:

- identify the actual development, result, release, correction, or debate;
- preserve the qualification needed to avoid a materially false impression;
- use attribution when the claim comes only from an interested party;
- remain compatible with the confidence expressed by the evidence packet;
- work alongside, rather than duplicate, source-type and review-status badges.

### Prohibited behavior

A display title MUST NOT:

- use unsupported superlatives such as “first,” “best,” or “largest”;
- use “breakthrough,” “revolutionary,” “game-changing,” or equivalent hype unless
  the wording itself is the subject of the story;
- turn correlation into causation;
- imply peer review, replication, or independent confirmation that does not exist;
- conceal that a result is limited to animals, simulations, a small sample, or
  another essential scope condition;
- use a question merely to manufacture curiosity;
- inherit unexplained acronyms when a short ordinary-language alternative exists.

### Attribution examples

```text
Weak:     A new model solves long-context reasoning
Better:   Anthropic reports better long-context reasoning in a new model

Weak:     Coffee prevents heart disease
Better:   A large observational study links coffee intake with lower heart risk
```

### Fallback order

If no valid generated display title exists, the reader uses:

1. the clearest eligible source title, with its source attribution;
2. otherwise the story working title;
3. otherwise the primary source title.

A failed title generation MUST NOT block publication.

## Glance contract

### Audience and duration

- Assumes no topic-specific familiarity.
- Targets approximately 30–60 seconds of reading.
- Corresponds internally to ELI5 without presenting that label to the reader.

### Required content

Glance MUST provide:

1. what happened;
2. the simplest accurate mental model;
3. why it might matter;
4. the one qualification most likely to change the reader’s interpretation.

It SHOULD use an analogy only when the analogy preserves the relevant mechanism.
Any necessary term SHOULD be defined at first use.

### Exclusions

Glance SHOULD omit:

- exhaustive methodological detail;
- long numerical result tables;
- secondary caveats that do not alter the basic interpretation;
- unexplained field jargon;
- historical background not needed for the central intuition.

Simple language MUST NOT become stronger certainty.

## Explain contract

### Audience and duration

- Assumes foundational familiarity with the field.
- Targets approximately 3–6 minutes of reading.
- Corresponds internally to ELI20.

### Required content

Explain MUST cover:

1. the problem or prior approach;
2. what is new;
3. how the approach works at an intuitive but field-aware level;
4. the key evidence or experimental result;
5. how it compares with the relevant baseline;
6. the important limitation and uncertainty.

It MAY use established field terminology without defining every basic term. It
SHOULD explain new, ambiguous, or paper-specific terminology.

### Relationship with Glance

Explain MUST stand alone for a reader who skips Glance. When read after Glance, it
SHOULD preserve the same conceptual spine and add resolution rather than reverse
the framing or repeat the simple version verbatim.

Explain is not an expanded abstract. It MUST reorganize the material around reader
understanding.

## Technical contract

### Eligibility

Technical is eligible only when:

- the story contains suitable primary research;
- accessible primary material is sufficient to inspect the method and evidence;
- the evidence packet distinguishes reported results from interpretation;
- the system can cite the relevant sections, figures, tables, or source items.

A paper title and abstract alone are normally insufficient.

### Audience and duration

- Assumes the central intuition is already established.
- Targets approximately 8–15 minutes of reading.
- Remains navigable by a capable reader outside the paper’s narrow specialty.

### Required structure

Technical SHOULD use a predictable structure:

1. **Orientation** — the central intuition in one compact paragraph;
2. **Problem formulation** — what is being solved or tested;
3. **Approach** — architecture, intervention, experimental design, or method;
4. **Evidence** — datasets, controls, baselines, measurements, and evaluation;
5. **Results** — quantitative findings with context;
6. **Ablations or alternatives** — what supports the claimed mechanism;
7. **Limitations** — scope, assumptions, missing comparisons, and uncertainty;
8. **Relation to prior work** — only when supported by bibliographic evidence;
9. **Prerequisites** — reusable concept links needed to follow the walkthrough.

Equations, algorithms, and detailed numbers SHOULD appear only when they improve
understanding of the claim.

### Progressive entry

Technical MUST be reachable from a distinct “Go technical” action after Glance or
Explain. It MUST also support a direct URL for sharing and returning readers.

The interface MUST NOT require proof that a reader completed an orientation.

## Cross-layer invariants

Across one evidence-packet version:

- factual claims MUST NOT contradict one another;
- certainty MUST NOT increase merely because the language becomes simpler;
- key numbers MUST retain compatible units, populations, and comparison frames;
- preprint and peer-review status MUST remain consistent;
- interested-party claims MUST remain attributed;
- a qualification whose omission would make Title or Glance materially misleading
  MUST remain visible at that layer;
- source and concept links MUST resolve to stable reader-visible records.

Title and Glance MAY be produced in one inexpensive generation request, but they
MUST be validated independently.

## Versioning and staleness

Each generated presentation records:

- story ID;
- evidence-packet ID and version;
- presentation layer;
- prompt version;
- model provider and model;
- generation status;
- validation status;
- creation time.

New evidence creates a new conceptual spine and new presentation candidates. The
reader continues showing the previous valid set until the replacement set is
validated. A partially generated new set MUST NOT create cross-version mixtures.

## Evidence-only behavior

When generation is unavailable or evidence is insufficient:

- the feed still shows a safe fallback title;
- the story still exposes source titles, source roles, dates, and links;
- the reader clearly states which explanations are not yet available;
- Technical is omitted when ineligible;
- no placeholder text is presented as a generated explanation.

## Evaluation rubric

Each candidate is scored on a small hand-reviewed set before broad generation.

| Dimension | Title | Glance | Explain | Technical |
| --- | --- | --- | --- | --- |
| Supported by evidence | Required | Required | Required | Required |
| Appropriate certainty | Required | Required | Required | Required |
| Audience fit | General | Newcomer | Field-aware | Investigative |
| Intuitive understanding | Useful | Central | Central | Preserved |
| Key evidence | Implied safely | Brief | Explained | Examined |
| Limitations | Essential only | Essential | Important | Thorough |
| Source provenance | Story-level | Claim-level | Claim-level | Section-level |

Automatic checks MAY reject length, missing citations, prohibited hype,
cross-layer number mismatches, or invalid status labels. Human evaluation remains
required to establish that the result is genuinely useful.

## High-risk subjects

Medical, health, safety, and other high-risk stories require stricter validation.
Presentations MUST report evidence and uncertainty rather than provide personal
advice. A simpler presentation MUST never remove a warning necessary to prevent a
harmful interpretation.
