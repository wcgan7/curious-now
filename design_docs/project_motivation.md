# Curious Now — Project Motivation & Core Idea

## Why this exists (the problem)

Science coverage is everywhere, but **understanding is scarce**:

- **Fragmented coverage:** the same underlying paper/result shows up across many outlets with different framing.
- **Duplicate noise:** syndicated reposts and near-identical articles flood feeds.
- **Hype + weak calibration:** press releases and early results often read like certainty; limitations are buried.
- **Missing context:** readers don’t get the “what is this, how does it work, why does it matter?” ladder.
- **No sense of time:** science evolves; follow-ups, retractions, and reversals rarely connect back to earlier coverage.

The result: people either skim headlines and leave confused, or they must do their own research to validate and connect the dots.

---

## The core idea (what Curious Now builds)

Curious Now is a **science news system** whose primary unit is a **StoryCluster** (one story, many sources), designed to make science coverage:

1. **Organized** (dedupe + clustering),
2. **Understandable** (Intuition → Deep Dive),
3. **Calibrated** (trust + uncertainty + anti-hype),
4. **Trackable over time** (what changed + lineage).

In practice:

- Ingest many sources (RSS/APIs first), normalize Items, and group them into **StoryClusters**.
- Each StoryCluster becomes a canonical page that lists evidence links and (later) adds structured explanations.
- Readers choose depth: a **one-sentence takeaway**, an **Intuition** explanation, and an optional **Deep Dive**.
- The UI is intentionally **calm and learning-oriented** (“quiet curiosity”), avoiding urgency mechanics.

---

## The differentiator (the “wedge”)

Many apps can aggregate links. Curious Now’s wedge is:

- **Canonical clustering** (reduce noise; unify coverage),
- **Understanding layer** (explain without hype; citations and guardrails),
- **Updates + lineage** (science as an evolving map, not isolated posts).

Everything else (personalization, notifications, mobile) builds on that foundation.

---

## Principles (non-negotiables)

- **Source-first:** every cluster links to originals; explanations must be evidence-backed.
- **Progressive disclosure:** Intuition first, technical depth on demand.
- **Transparency:** content type labels (preprint vs peer-reviewed vs press release vs news) are visible.
- **Anti-hype by default:** limitations, sample size, animal-only results, and “not peer reviewed” disclaimers are not optional.
- **Canonical units:** updates, ranking, topic pages, and future notifications attach to StoryClusters.

---

## Shared vocabulary (used across the design docs)

- **Source:** a publisher/provider (journalism outlet, university, journal, preprint server).
- **Item:** one fetched piece of content (article, press release, preprint entry, report link).
- **StoryCluster:** a canonical “story page” grouping Items covering the same underlying paper/result/event.
- **Topic:** a taxonomy label for browsing/following.
- **Glossary entry:** a just-in-time definition used to reduce jargon.
- **Update log:** a record of meaningful changes to a cluster over time (“what changed”).
- **Lineage:** a graph/timeline linking related papers/models/ideas (extends/contradicts/etc.).
