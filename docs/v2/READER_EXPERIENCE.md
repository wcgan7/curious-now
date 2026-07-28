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
- urgency styling unrelated to evidence;
- an image added merely to increase card prominence.

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
│  │ Why it matters                              │  │ STATUS                 │  │
│  │ ...                                         │  │ Preprint               │  │
│  │                                             │  │ Not independently      │  │
│  │ Important qualification                     │  │ confirmed              │  │
│  │ ...                                         │  └────────────────────────┘  │
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
│ Important limitation         │
│ ...                          │
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
- A local preference MAY remember the most recently selected orientation, but v2
  defaults new stories to Glance and does not infer expertise.
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

## Current prototype delta

The checked-in `apps/reader/` application predates this approved contract. It
currently:

- renders Glance or evidence-only text inside feed cards;
- exposes depth pills in the feed;
- treats Technical as an equal story-page tab;
- reads `stories.canonical_title` directly as the display title.

The next implementation pass must:

1. make feed cards title-only;
2. separate source, working, and display titles;
3. default opened stories to Glance;
4. limit the orientation selector to Glance and Explain with familiarity labels;
5. move Technical into a progressive continuation;
6. retain evidence-only behavior without empty controls.

These are known prototype differences, not alternative product behavior.
