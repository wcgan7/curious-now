# Curious Now v2 — Reader Experience

## Product intent

The reader should feel like a calm shelf of scientific developments rather than a
conventional news homepage. Scrolling is for discovery; opening a story is an
intentional transition into understanding.

The primary information architecture is:

```text
Feed                         Story                         Deep dive

Display title        ->      Glance <-> Explain    ->     Technical
trust metadata               source shelf                  evidence + prerequisites
```

## Interaction principles

1. The feed optimizes for scanning titles, not consuming summaries.
2. Opening a story defaults to Glance.
3. Glance and Explain are peer orientation choices for different familiarity.
4. Technical is progressively disclosed after orientation.
5. Evidence and original titles remain available at every story depth.
6. AI failure reduces enrichment, never access to sources.
7. Familiarity is chosen per story; it is not silently inferred as a permanent
   user trait.

## Feed

### Desktop wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ curious.now                  science worth understanding              Latest │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  A better thing to scroll.                                                   │
│  Continuously collected science, ready when curiosity wins.                  │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ THE LIVE SHELF                                                 29 JUL 2026   │
├──────────────────────────────────────────────────────────────────────────────┤
│ 01  PREPRINT · ARTIFICIAL INTELLIGENCE                                      │
│                                                                              │
│     A new attention design preserves information                            │
│     from earlier layers                                                      │
│                                                                              │
│     Google Research · 3 hours ago                                      →     │
├──────────────────────────────────────────────────────────────────────────────┤
│ 02  PEER REVIEWED · ASTRONOMY                                                │
│                                                                              │
│     A nearby planet may have retained a surprisingly                         │
│     dense atmosphere                                                         │
│                                                                              │
│     Nature · 5 hours ago                                                →     │
├──────────────────────────────────────────────────────────────────────────────┤
│ 03  LAB ANNOUNCEMENT · BIOLOGY                                               │
│                                                                              │
│     A protein model predicts interactions from sequence                      │
│                                                                              │
│     DeepMind · Paper attached · 7 hours ago                            →     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Mobile wireframe

```text
┌──────────────────────────────┐
│ curious.now           Latest │
├──────────────────────────────┤
│                              │
│ A better thing to scroll.    │
│                              │
├──────────────────────────────┤
│ PREPRINT · AI                │
│                              │
│ A new attention design       │
│ preserves information from   │
│ earlier layers               │
│                              │
│ Google Research · 3h     →   │
├──────────────────────────────┤
│ PEER REVIEWED · ASTRONOMY    │
│                              │
│ A nearby planet may have     │
│ retained a surprisingly      │
│ dense atmosphere             │
│                              │
│ Nature · 5h              →   │
└──────────────────────────────┘
```

### Feed-card contract

A feed card contains:

- source/review-status badge;
- optional broad topic label;
- display title;
- principal source identity;
- relative publication time;
- optional neutral “paper attached” indicator;
- one clear affordance to open the story.

A feed card does not contain:

- a Glance excerpt;
- equal Glance, Explain, and Technical buttons;
- a technical-availability call to action;
- engagement counts or reactions;
- urgency styling unrelated to evidence.

### Images on cards

An earlier version of this document prohibited "an image added merely to
increase card prominence". That rule is withdrawn, because it mistook the
mechanism for the harm.

The harm it aimed at is a feed that competes for attention. The mechanism it
banned — a picture — turns out to serve the opposite purpose. Principle 1 says
the feed optimizes for scanning, and a column of forty text cards is harder to
scan than one where the eye has something to travel by. Uniformity is not calm;
it is undifferentiated, and the reader pays for it in effort.

A feed card MAY therefore show the image its source syndicated with the story —
the `media:content`, `media:thumbnail`, or image `enclosure` a publisher puts in
its own feed precisely so that a reader can display it.

- The image MUST come from the feed. It MUST NOT be scraped from the page,
  generated, or substituted from stock.
- It MUST NOT be the reason to open a story: the display title remains the
  card's subject, and the image is subordinate to it in size and in position.
- A story with no syndicated image MUST render as a complete card, not as a card
  with a hole in it. Around half the corpus has none — no preprint server or
  journal syndicates one — so the absence is the common case, not the exception.
- A broken or unreachable image MUST degrade to that same complete card.

The whole semantic card acts as one story link. External source links begin on the
story page so nested interactive controls do not fragment the feed.

## Story orientation

### Glance state — desktop

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Back to feed                                                               │
│                                                                              │
│ PREPRINT · PRIMARY RESEARCH                                                  │
│ A new attention design preserves information                                │
│ from earlier layers                                                          │
│ Google Research · 3 hours ago · 2 sources                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────┐  ┌────────────────────────┐  │
│  │ [ Glance · New to this ] [ Explain · Know ] │  │ SOURCE SHELF           │  │
│  │                                             │  │                        │  │
│  │ GLANCE                                      │  │ 01 Original paper      │  │
│  │                                             │  │    Original title  ↗   │  │
│  │ Attention lets a model decide which pieces  │  │                        │  │
│  │ of information matter right now. The new    │  │ 02 Lab announcement   │  │
│  │ design gives it a way to keep useful...     │  │    Source title    ↗   │  │
│  │                                             │  │                        │  │
│  │ information across a long input, which the   │  │ STATUS                 │  │
│  │ usual design discards. It was tested on one │  │ Preprint               │  │
│  │ model family, so whether it holds more      │  │ Not independently      │  │
│  │ widely is still open.                       │  │ confirmed              │  │
│  │                                             │  └────────────────────────┘  │
│  └─────────────────────────────────────────────┘                              │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Want to investigate the actual work?                                  │  │
│  │ Technical walkthrough · 11 min                                        │  │
│  │ Methods, experiments, results, and limitations          [ Go deeper → ]│  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Orientation selector

The selector contains only:

- `Glance` with the descriptor `New to this`;
- `Explain` with the descriptor `Know the field`.

Glance is selected on first open. Selecting Explain replaces the orientation body
without changing the title, evidence version, or source shelf.

The selector uses visible buttons with tab semantics. Swiping MAY be added as a
secondary gesture but MUST NOT be the only way to change orientation.

### Explain state — mobile

```text
┌──────────────────────────────┐
│ ← Feed                       │
│                              │
│ PREPRINT · AI                │
│ A new attention design       │
│ preserves information from   │
│ earlier layers               │
│                              │
│ [ Glance ] [ Explain ● ]     │
├──────────────────────────────┤
│ EXPLAIN · KNOW THE FIELD     │
│                              │
│ Existing transformer blocks │
│ normally pass information... │
│                              │
│ What changed                 │
│ ...                          │
│                              │
│ Evidence and comparison      │
│ ...                          │
│                              │
│ ...tested on one model       │
│ family, so how far it        │
│ generalises is still open.   │
├──────────────────────────────┤
│ TECHNICAL WALKTHROUGH        │
│ Methods and results · 11 min │
│                 Go deeper →  │
├──────────────────────────────┤
│ Sources and evidence         │
└──────────────────────────────┘
```

Explain is self-contained. A reader who moves from Glance to Explain should
recognize the same core intuition and receive more resolution rather than an
unrelated second summary.

## Technical entry

Technical is not included in the Glance/Explain segmented control. It appears as a
separate continuation after the orientation content.

The call to action includes:

- the label `Technical walkthrough`;
- an estimated reading time;
- a short description such as `Methods, experiments, results, and limitations`;
- a clear `Go deeper` action.

If Technical is ineligible, the reader omits the promotional card. The source
shelf MAY state why no deep dive is available, for example `Abstract only` or
`No accessible primary paper`.

## Technical reader

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Back to Explain                         TECHNICAL WALKTHROUGH · 11 MIN      │
│                                                                              │
│ A new attention design preserves information from earlier layers            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1  Orientation                      PREREQUISITES                            │
│     Central intuition in one         Attention                               │
│     compact paragraph.               Query, key, and value                    │
│                                     Residual connections                     │
│  2  Problem formulation                                                     │
│     ...                              EVIDENCE                                 │
│                                     Figure 2 · Original paper ↗              │
│  3  Approach                                                               │
│     ...                              STATUS                                  │
│                                     Preprint · Not replicated                │
│  4  Experimental design                                                     │
│     ...                                                                      │
│                                                                              │
│  5  Results and comparisons                                                  │
│     ...                                                                      │
│                                                                              │
│  6  Limitations                                                              │
│     ...                                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

Technical has its own stable URL. A shared deep link opens directly, while still
showing a compact orientation and a route back to Glance or Explain.

## Evidence-only state

When no valid generated orientation exists:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAB ANNOUNCEMENT                                                             │
│ Source title used as the story title                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ SOURCES AVAILABLE                                                            │
│                                                                              │
│ A grounded explanation is not available yet. Read the original source or     │
│ return later after the evidence has been processed.                          │
│                                                                              │
│ [ Open original source ↗ ]                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The reader does not show empty orientation tabs, invented placeholder summaries,
or a Technical action.

## Navigation and state

- Opening a feed card defaults to `glance`.
- `?view=glance` and `?view=explain`, or equivalent stable routes, SHOULD support
  refresh and sharing.
- Technical uses a stable deep-linkable route.
- Returning to the feed SHOULD restore the previous scroll position.
- Switching orientation SHOULD retain the story-header position on small screens.
- A local preference MAY remember the orientation last selected within a story,
  so returning to that story restores it. A newly opened story always defaults to
  Glance; v2 does not carry an orientation choice across stories or infer
  expertise.
- New evidence MUST NOT switch the visible presentation halfway through a reading
  session.

## Trust presentation

The story header and source shelf make the following distinctions visible:

- preprint versus peer reviewed;
- primary research versus lab or institutional announcement;
- first-party versus independent coverage;
- accessible full text versus abstract or metadata only;
- current evidence version and correction status when relevant.

Trust information uses plain labels, not opaque universal quality scores.

## Accessibility

- Feed cards, orientation controls, and deep-dive actions are keyboard reachable.
- Orientation controls expose tab roles and selected state.
- Status is communicated by text in addition to color.
- External links state that they open original sources.
- Reading widths, line height, and text scaling support long-form comprehension.
- Reduced-motion preferences disable nonessential transitions.
- Technical equations and figures require textual alternatives.

### Equations in Technical

Technical may use an equation where it materially improves understanding, so
the reader must typeset one properly rather than printing raw markup. TeX
survives retrieval from arXiv's LaTeXML rendering and from JATS, and is the
form stored, so the reader renders TeX and supplies the textual alternative the
accessibility rule requires.

Math does not survive the PDF path: glyph positions carry no notation, so a
paper resolved from PDF yields prose without usable equations. Technical for
such a paper is still worth producing; it simply cannot show the mathematics,
and should not paraphrase an equation it cannot display.

## Current prototype delta

The checked-in `apps/reader/` application follows the approved reading flow:
title-only feed cards that act as one story link, Glance as the opened default,
a Glance/Explain orientation selector with familiarity labels, Technical as a
progressive continuation with a shareable `?view=technical` route, and
evidence-only stories without empty controls. The data layer separates source,
working, and display titles and keeps showing the newest fully validated
presentation set.

Remaining known deltas, pending later milestones:

- concept chips are informational only; concept cards and tap-through
  navigation are not built;
- the Technical body renders one text column, not yet the structured
  walkthrough sections with per-section evidence links;
- topics and highlighted-story explanations have no reader UI; search covers
  story, display, and source titles but has no topic or date filters;
- claim-level provenance is not reader-facing. It was rendered as a numbered
  claim ledger — every extracted claim with its kind and a confidence
  percentage — which put the pipeline's internal record on the page in the
  pipeline's own vocabulary. The evidence packet still holds it, and the source
  shelf still links every source; the intended form is provenance inline in the
  explanation, which is not built.

These are known prototype differences, not alternative product behavior.
