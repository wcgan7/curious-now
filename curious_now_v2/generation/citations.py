"""Why a paper cited the work it cited.

A citation graph records that A cites B. It never records why, and the why is
what a reader following a line of work actually needs: most citations are
perfunctory background, and the few that matter are the ones a paper builds on,
borrows a method from, or argues with. Studies of citation function find the
large majority are the former, so an untyped edge list buries the six edges
that carry meaning under the ninety-four that do not.

Nothing external can supply this. Typing an edge means reading the sentence
that made the citation, which is why bibliographic databases index the edge and
stop there — and why we can go further, having read the paper.

Two measurements shaped the design. Frequency alone is a poor filter: a paper
names the method it depends on once and its related work eight times, so the
single mention is often the load-bearing one. Cue phrases -- "we use the method
of", "in contrast to" -- are the opposite: precise where they appear and absent
from 94.5% of citations. Neither can gate, so neither does. Every reference is
shown, both signals travel with it as hints, and the model decides.

The edge is what the CITING paper claims. We read A, not B, so "A extends B" is
A's account of itself, grounded in A's own sentence. That is honest and
checkable, and it becomes more than that later: once B has been read too, the
claim can be tested against B, and "cited for something the cited paper does not
say" is a finding no bibliographic database can produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from curious_now_v2.generation.client import Completion, Generator

PROMPT_VERSION = "citations-v1"

# The relations paper_relations already allows. "cites" is the untyped default
# and is never emitted: an edge worth storing is one that says something more
# than that a citation exists.
TYPED_RELATIONS = ("extends", "applies", "replicates", "contradicts")

# A paper's bibliography is shown whole up to this point. Beyond it the least
# cited entries are dropped, and how many were dropped is reported rather than
# passed over -- a truncated list that looks complete is worse than a short one.
MAX_SHOWN = 120
# What one paper may claim as load-bearing. A paper genuinely leaning on forty
# others is describing background, not dependency.
MAX_TYPED = 12
MIN_QUOTE_WORDS = 5
CITATION_CHARS = 150
CONTEXTS_SHOWN = 2

# Precise where present, absent from most citations. Used only to choose which
# stored sentence to show, never to decide what counts.
_CUES = (
    "we use", "we used", "we adopt", "we adapted", "we follow", "following",
    "as described in", "as described by", "based on", "using the method",
    "we extend", "we build on", "builds on", "building on",
    "in contrast to", "unlike", "contrary to", "fails to", "differs from",
    "consistent with", "in agreement with", "replicates", "confirms",
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["edges"],
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ref", "relation", "quote", "reason"],
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "The [n] tag of the reference, exactly as shown",
                    },
                    "relation": {
                        "type": "string",
                        "enum": list(TYPED_RELATIONS),
                    },
                    "quote": {
                        "type": "string",
                        "description": (
                            "Verbatim sentence from this paper that establishes "
                            "the relation"
                        ),
                    },
                    "reason": {"type": "string"},
                },
            },
        }
    },
}

PROMPT = """You are reading one paper's bibliography for Curious Now, a calm \
feed of science worth understanding.

Most citations in any paper are background: the field is introduced, prior work \
is acknowledged, and nothing depends on them. A few are load-bearing — the \
paper builds on them, takes a method or dataset from them, confirms them, or \
argues against them. Your job is to find only those few, and to show where the \
paper says so.

Choose a relation for each one you pick:

- extends: this paper takes that work further — a stronger result, a \
generalisation, the next step in the same line.
- applies: this paper uses something from that work — its method, model, \
dataset, instrument, or protocol.
- replicates: this paper confirms or reproduces that work's finding.
- contradicts: this paper's result disagrees with that work, or the paper says \
that work is wrong or insufficient.

Rules that matter:

1. QUOTE, VERBATIM, from the sentences shown for that reference. The quote must \
be the sentence where the paper establishes the relation. If you cannot find \
one, do not include the reference. A relation you cannot point at is a guess, \
and a guess here is worse than a gap.
2. HOW OFTEN A REFERENCE IS CITED IS ONLY A HINT. A paper names the method it \
depends on once and its related work eight times. A reference cited a single \
time in the methods is frequently the most important one in the paper. Do not \
prefer the high counts.
3. A FAMOUS PAPER IS NOT AUTOMATICALLY LOAD-BEARING. Judge the role it plays \
in THIS paper, from THIS paper's sentences.
4. Return at most {max_typed}. Returning three well-evidenced relations is a \
better answer than twelve thin ones, and returning none is a valid answer for \
a paper that genuinely only surveys.

PAPER: {title}

REFERENCES:
{references}
"""


@dataclass(frozen=True)
class CitedWork:
    """A stored bibliography entry, as the typing pass sees it."""

    ref_key: str
    label: str | None
    citation_text: str
    doi: str | None
    arxiv_id: str | None
    mentions: int
    cited_sections: tuple[str, ...]
    contexts: tuple[str, ...]

    @property
    def identifier(self) -> str | None:
        if self.doi:
            return f"doi:{self.doi}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        return None

    def best_contexts(self, limit: int = CONTEXTS_SHOWN) -> tuple[str, ...]:
        """The sentences most likely to state why the citation was made."""

        ranked = sorted(
            self.contexts,
            key=lambda sentence: (
                not any(cue in sentence.casefold() for cue in _CUES),
                -len(sentence),
            ),
        )
        return tuple(ranked[:limit])


@dataclass(frozen=True)
class TypedEdge:
    ref_key: str
    relation: str
    quote: str
    reason: str


@dataclass(frozen=True)
class TypingResult:
    edges: tuple[TypedEdge, ...]
    completion: Completion
    shown: int = 0
    dropped: int = 0
    rejected: tuple[str, ...] = field(default_factory=tuple)


def _flat(value: str) -> str:
    return " ".join(value.split()).casefold()


def selected(works: list[CitedWork], limit: int = MAX_SHOWN) -> tuple[list[CitedWork], int]:
    """The references to show, and how many were left out.

    Only a bibliography past the limit is trimmed, and it is trimmed by mention
    count because an entry the body never cites cannot have a sentence
    establishing a relation anyway.
    """

    if len(works) <= limit:
        return list(works), 0
    ordered = sorted(works, key=lambda work: (-work.mentions, work.ref_key))
    return ordered[:limit], len(works) - limit


def render_references(works: list[CitedWork]) -> str:
    """One compact block per reference, with both signals attached as hints."""

    lines: list[str] = []
    for index, work in enumerate(works, start=1):
        sections = ", ".join(work.cited_sections) or "unknown"
        head = (
            f"[{index}] cited {work.mentions}x"
            f" | sections: {sections}"
            f" | {work.citation_text[:CITATION_CHARS]}"
        )
        lines.append(head)
        for sentence in work.best_contexts():
            lines.append(f'      "{sentence}"')
        if not work.contexts:
            lines.append("      (no in-text citation recovered)")
    return "\n".join(lines)


def _validate(
    payload: dict[str, Any], shown: list[CitedWork]
) -> tuple[tuple[TypedEdge, ...], tuple[str, ...]]:
    """Keep only edges that name a real reference and quote its own text."""

    by_tag = {str(index): work for index, work in enumerate(shown, start=1)}
    edges: list[TypedEdge] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for entry in payload.get("edges") or []:
        if not isinstance(entry, dict):
            continue
        tag = str(entry.get("ref") or "").strip().strip("[]")
        relation = str(entry.get("relation") or "").strip()
        quote = " ".join(str(entry.get("quote") or "").split())
        reason = str(entry.get("reason") or "").strip()

        work = by_tag.get(tag)
        if work is None:
            rejected.append(f"[{tag}] no such reference")
            continue
        if relation not in TYPED_RELATIONS:
            rejected.append(f"[{tag}] relation {relation!r} not allowed")
            continue
        if work.ref_key in seen:
            rejected.append(f"[{tag}] duplicate")
            continue
        if len(quote.split()) < MIN_QUOTE_WORDS:
            rejected.append(f"[{tag}] quote too short to check")
            continue
        # The quote must come from a sentence that actually cited this entry.
        # Without this the relation is an assertion about a paper the model has
        # not read, attached to a reference it chose freely.
        if not any(_flat(quote) in _flat(sentence) for sentence in work.contexts):
            rejected.append(f"[{tag}] quote is not in this reference's citing text")
            continue

        seen.add(work.ref_key)
        edges.append(TypedEdge(work.ref_key, relation, quote, reason))
        if len(edges) >= MAX_TYPED:
            break

    return tuple(edges), tuple(rejected)


def type_citations(
    generator: Generator,
    *,
    title: str,
    works: list[CitedWork],
) -> TypingResult:
    """Ask which references this paper leans on, and make it show where."""

    cited = [work for work in works if work.contexts]
    if not cited:
        # Nothing was linked to the body, so no sentence exists to ground a
        # relation. This is the ordinary case for a PDF-derived bibliography,
        # and it costs nothing to decline before paying for a call.
        return TypingResult(
            (), Completion(payload=None, error="no citation contexts"), 0, 0
        )

    shown, dropped = selected(cited)
    completion = generator.complete(
        PROMPT.format(
            title=title,
            references=render_references(shown),
            max_typed=MAX_TYPED,
        ),
        SCHEMA,
    )
    if not completion.ok:
        return TypingResult((), completion, len(shown), dropped)

    edges, rejected = _validate(completion.payload or {}, shown)
    return TypingResult(edges, completion, len(shown), dropped, rejected)


DECLINED = re.compile(r"^no citation contexts")
