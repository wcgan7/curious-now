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

## Story kinds

A story may cover a development, result, release, correction, or debate, drawn
from any science source — not only research papers. The layer contracts below
apply to every kind: their required-content lists name roles a presentation must
fill, not a paper-shaped template.

- For a result, the mechanism is what produces the finding, and the comparison
  is the prior state of evidence or the relevant baseline.
- For a release, they are how the new capability works and what was previously
  available.
- For a correction, they are why the original conclusion failed and what was
  previously believed.
- For a debate, they are what each position claims follows from the evidence,
  and where the positions actually diverge.

A required element that is genuinely inapplicable to a story kind MAY be omitted;
it MUST NOT be satisfied with invented material.

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
3. otherwise the primary source title, with its source attribution.

A source title is eligible when it does not violate the prohibited-behavior rules
above. A fallback that reaches step 3 MAY show a title that would fail the
display-title contract, because a source’s own headline is an attributed fact
rather than Curious Now editorial text; it MUST remain visibly attributed to its
source. A fallback source title MUST NOT be edited into partial compliance — it
is shown verbatim or not at all.

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

Explain answers one question: **how does it work?**

Each layer owes the reader a different question. Glance answers what happened
and why it might matter. Explain answers how. Technical answers whether it holds
up. A reader who already knows the field does not need the problem restated;
what they lack is the mechanism of this particular development.

Explain MUST:

1. explain the mechanism at an intuitive but field-aware level — what the
   approach actually does, and why that produces the claimed effect;
2. carry the qualification that keeps the mechanism honest.

Explain SHOULD, when the evidence supports it:

- frame the problem or prior approach, only as far as the mechanism needs;
- state what is genuinely new about it;
- give the key evidence that the mechanism works;
- compare with the relevant baseline or prior state of understanding.

An unsupported SHOULD element is omitted. It is never filled with invented
material or generic restatement.

The qualification is required because a vivid mechanical account reads as
truth: explaining precisely how something works, while saying nothing about
what is uncertain, produces confidence that the evidence has not earned. Since
Technical is often unavailable, Explain is frequently the deepest layer a reader
sees.

The qualification MAY be satisfied from source metadata rather than an extracted
claim — preprint status, a single source, or interested-party-only reporting all
qualify a mechanism — so it constrains what Explain says without gating whether
Explain exists.

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

- the story contains suitable primary material — a paper, preprint, technical
  report, dataset, or equivalent primary documentation, not only coverage of it;
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

## Sufficiency and abstention

A layer is produced only when the evidence supports every element that layer
requires. Generation MUST be able to decline a layer, and declining MUST be
recorded with the element that was unsupported.

Sufficiency is judged per required element, never as a single global
"is this enough" question:

- each required element resolves to one or more supported claims in the
  evidence packet, or it is unsupported;
- an unsupported required element makes that layer ineligible;
- eligibility is decided from the recorded per-element result, not from the
  generator's overall confidence.

This ordering keeps each check where it is reliable:

1. a deterministic text gate rejects material that cannot ground anything,
   before any inference is spent;
2. evidence-packet extraction records which elements the sources actually
   support;
3. depth planning derives eligible layers from those recorded elements;
4. generation MAY still decline, and a declined layer is recorded rather than
   produced.

Distinguish two reasons an element may be absent. An element that is genuinely
inapplicable to the story kind MAY be omitted, as described in Story kinds. An
element that is applicable but unsupported by the available evidence MUST cause
the layer to be declined. Neither may be satisfied with invented material,
generic hedging, or restatement that presents thin evidence as thorough.

Declining one layer MUST NOT withdraw a shallower layer. A story whose evidence
supports Glance but not Explain publishes with Glance alone.

Abstention counts and their reasons MUST be visible to the operator. A layer
declined often for the same missing element indicates a retrieval gap rather
than a generation failure.

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
- conceptual-spine ID and version;
- presentation layer;
- prompt version;
- model provider and model;
- generation status;
- validation status;
- creation time.

New evidence creates a new conceptual spine and new presentation candidates. A
spine MAY also be regenerated for an unchanged evidence packet, for example after
a prompt improvement; the regenerated spine receives a new version. The reader
continues showing the previous valid set until the replacement set is validated.
A displayed set MUST come from one evidence-packet version and one
conceptual-spine version; a partially generated new set MUST NOT create
cross-version mixtures.

## Evidence-only behavior

When generation is unavailable or evidence is insufficient:

- the feed still shows a fallback title chosen by the title fallback order;
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
