# Curious Now v2

This directory is the source of truth for the v2 rebuild.

Read in this order:

1. [`PRODUCT.md`](PRODUCT.md) — the product promise, reader loop, and v2 scope
2. [`PRESENTATION_CONTRACT.md`](PRESENTATION_CONTRACT.md) — normative rules for
   Title, Glance, Explain, and Technical
3. [`READER_EXPERIENCE.md`](READER_EXPERIENCE.md) — feed, story, and deep-dive
   wireframes
4. [`ARCHITECTURE.md`](ARCHITECTURE.md) — the lean runtime and data flow
5. [`PORTING.md`](PORTING.md) — what is retained from v1 and what is deliberately
   left behind
6. [`OPERATIONS.md`](OPERATIONS.md) — local commands, scheduled deployment, and
   cost controls

The legacy implementation is preserved by the `legacy-v0` Git tag. During the
transition, v1 remains runnable, but new product behavior must follow these v2
documents rather than the old stage roadmap.
