# Curious Now v2 — Concepts: what was measured, and what is still open

**Status: not built, and now measured as not worth building in this form.**
`concepts`, `concept_aliases`, `concept_edges` and `story_concepts` exist and
hold nothing. This records what was learned, including the experiment that
settled it.

## The want

A reader who has just understood something should be able to move along the
idea rather than back to the feed: from residual attention to attention, from
attention to deep learning. Two motivations were given for it. The second —
building a queue of papers worth ingesting — has since been served a different
way, by the citation graph. The first has not been served at all.

## What was measured

**Extracted prerequisites are not a vocabulary.** Every generated spine already
lists what a reader needs to know first, and there were 1,228 distinct strings
across 203 spines. **93% of them appeared exactly once.** Normalising case and
articles merged 22. They read as what they are — a reading aid written for one
story:

```
Heavy-tailed distributions and bounded p-th central moments
A limited food supply can create tension within a group.
```

Promote those to nodes and the result is 1,228 concepts holding one story each,
joined by nothing.

**The v1 taxonomy cannot resolve them.** It looked like a free head start: 13
categories, 55 subtopics, 491 curated aliases. It resolved **17 of 1,228, or
1%**. Worse, 106 of its 443 normalised aliases are claimed by more than one
node, because they were written for coarse one-of-thirteen tagging rather than
for naming ideas — `transformer` belongs to both Artificial Intelligence and
NLP, `deep learning` to the AI category itself. Imported as concept aliases,
the ladder collapses on the very example that motivated it.

**External vocabularies disambiguate for free, and are noisy.** Wikidata holds
the two senses of "attention" as separate entities — Q103701642, a transformer
mechanism, and Q6501338, a cognitive process — and `subclass of` climbs from
each without anyone authoring a hierarchy. But OpenAlex's concept tagger scored
`Context (archaeology)` at 0.68 on a neuroscience paper, above any threshold
worth setting, and its top-scored concept for two chemistry papers was
`Chemistry`. Raw external tags are not shippable.

## What follows from that

A concept chip should be shown only when its label appears in the story's own
text. `Context (archaeology)` never appears in a neuroscience story;
`perineuronal net` is all over it. That is the same grounding discipline the
rest of the pipeline already uses — claim excerpts, qualification spans and
Technical citations all validate by presence in source text — and it costs
nothing.

Generic concepts make poor destinations. Anything at OpenAlex level 0 or 1 is a
category wearing a concept's clothes.

## The proposed fix was tried, and it does not work

Asking extraction for concepts named as a textbook index would name them --
capped at four per story, each with the next rung up, and told explicitly that a
name is useful only if another paper on a different subject would be listed
under it -- was the remaining hope. It was run over 100 published stories for
about a dollar.

**95% of the names were used exactly once.** Slightly worse than the 93%
baseline it was meant to beat.

```
350 distinct names from 100 stories
334 used exactly once   (95%)     3 used by 3+ stories
```

The reason is not the prompt. It is that **reuse requires topical density this
corpus does not have and should not have.** Curious Now reads thirteen
categories on purpose; two papers rarely turn on the same specific idea. At
1.06 uses per name, adding stories does not fix it -- extrapolating to the full
corpus gives perhaps 33 concepts reaching three stories, which is not a web.

What did recur is the level above:

```
9  machine learning        4  public health
7  artificial intelligence 4  galaxy evolution
```

Field-level names repeat because fields repeat. But only **17 of 303** broader
names appear as anyone's concept, so the two do not chain into a ladder: asked
for one step up, the model reaches straight for a field.

That is the finding. The upper rungs are real and we already get them free from
OpenAlex topics via an identifier. The rung the original request actually wanted
-- residual attention to attention, one step of genuine abstraction -- is the one
the corpus cannot support.

## What was built instead

Typed citation edges: `paper_relations`, 2,012 of them, each carrying the
verbatim sentence that established it. That gives lineage — what a paper
extends, applies, replicates or contradicts — and a ranked queue of works many
read papers depend on but we have not fetched.

It does not give abstraction. A reader can walk from a paper to the work it
builds on, but not from residual attention up to attention. The two are
different structures serving different questions, and only one of them exists.
