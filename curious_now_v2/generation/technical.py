"""The fourth rung: an inspection of the work rather than an account of it.

Glance and Explain are orientation — what happened, and how it works. Technical
answers a different question: does it hold up. Its reader has decided to look
at the evidence, so this layer is the only one that cites: sections, figures and
tables, named exactly as retrieval recovered them.

That citation is what keeps the layer honest, and it is checkable. Retrieval
already stores the document's structure map, so a label the model invents can
be caught against the labels the document actually has — which is the same
grounding used for claim excerpts and the qualification span, applied to the
one layer whose whole purpose is to be checked against the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from curious_now_v2.generation.client import (
    Completion,
    Generator,
    unescape_newlines,
)

PROMPT_VERSION = "technical-v5"

# A shape that usually works, offered to the writer and enforced on nobody.
# The contract says a walkthrough SHOULD be predictable, not that it must use
# these words: a proof has a proof strategy, a cohort study has a cohort, and a
# fabricated device has a fabrication process. Requiring these exact eight
# would have cost such a paper its whole Technical layer over a heading.
SUGGESTED_HEADINGS = (
    "Orientation",
    "Problem formulation",
    "Approach",
    "Evidence",
    "Results",
    "Ablations or alternatives",
    "Limitations",
    "Relation to prior work",
)

# Eight to fifteen minutes of reading, per the contract. Unlike Explain's, this
# floor is meaningful: a walkthrough that inspects methods, evidence, results
# and limitations in under six hundred words has not inspected them.
MIN_WORDS = 600
MAX_WORDS = 2500

# A heading names a part; a sentence is not a heading. This is the only shape
# check left on them, and it exists so the reader's map through several
# thousand words stays scannable.
MAX_HEADING_WORDS = 8

_MATH_MARKER = re.compile(r"\[(equation|expression)\]")

# How a float is shown to the writer: "Figure 4 — what it shows". The writer
# is asked to cite the label alone, and citing the whole line back is a
# reasonable thing to do when the whole line is what it was shown, so the
# matcher accepts either. Getting this wrong rejected an entire walkthrough
# for citing its four tables correctly.
LABEL_SEPARATOR = " — "

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "sections",
        "prerequisites",
        "citations",
        "eligible",
        "declined_reason",
    ],
    "properties": {
        "eligible": {"type": "boolean"},
        "declined_reason": {"type": "string"},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "used_for"],
                "properties": {
                    "label": {"type": "string"},
                    "used_for": {"type": "string"},
                },
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "text"],
                "properties": {
                    "heading": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
}

PROMPT = """You are writing the Technical walkthrough for Curious Now, a calm \
feed of science worth understanding.

This reader has read an orientation already and has chosen to look at the work \
itself. The question this layer answers is whether it holds up.

Work ONLY from the SOURCE TEXT. Do not use outside knowledge.

Write 600-2500 words total under headings of your choosing. Use the headings \
this work calls for — a proof has a proof strategy, a cohort study has a \
cohort, a fabricated device has a fabrication process — and keep each to a few \
words, because they are the reader's map through several thousand.

This shape usually works and is a good default where nothing better suggests \
itself:
  Orientation, Problem formulation, Approach, Evidence, Results,
  Ablations or alternatives, Limitations, Relation to prior work

What matters is not the labels but the progression: orient the reader, say what \
was done, show what it rests on, give what was found, and be clear about what \
it does not settle. However you name them, a reader must be able to find those \
things, and must meet them in that order — the sequence is the argument.

Remain an intuitive walkthrough, not a compressed paper. The reader knows the \
field; they do not know this work.

Mathematics belongs here where it carries the argument — an equation the paper \
turns on, a rate, a threshold, a magnitude — and nowhere it does not. Quote it \
as it appears in the source, KEEPING the \\( \\) or \\[ \\] delimiters around \
it. Those delimiters are how the reader's typesetter knows where a formula \
starts and ends; without them it prints backslashes at the reader. Never write \
mathematics outside them. `[equation]` and `[expression]` mark mathematics \
that could not be recovered from the source format: never pass those markers \
to the reader and never say what the missing equation states.

The STRUCTURE MAP below gives each figure and table with its caption, so you \
know what each one shows. Where a figure carries the argument, say what it \
shows at the point it matters — a reader who cannot see it should still learn \
what it demonstrates.

In `citations`, list the sections, figures, and tables you actually drew on. \
Give the LABEL ONLY — the short name at the start of the map entry, before the \
dash, such as "Figure 4" or "Methods" — never the caption after it. Say what \
you used each for in `used_for`. Do not cite anything absent from that map; an invented \
citation is worse than no citation, because this is the layer a reader opened \
in order to check.

In `prerequisites`, list the concepts a capable reader outside this speciality \
would need in order to follow the walkthrough.

If the source cannot support an inspection of the method and evidence, set \
eligible to false and say why in declined_reason. Declining is correct whenever \
the text is an account of the work rather than the work.

SOURCE: {source_name} ({content_type})
TITLE: {title}

STRUCTURE MAP
Sections: {sections}
Figures: {figures}
Tables: {tables}

SOURCE TEXT:
{full_text}
"""


@dataclass(frozen=True)
class TechnicalSection:
    heading: str
    text: str


@dataclass(frozen=True)
class Citation:
    label: str
    used_for: str


@dataclass(frozen=True)
class Technical:
    sections: tuple[TechnicalSection, ...]
    citations: tuple[Citation, ...]
    prerequisites: tuple[str, ...]
    eligible: bool
    declined_reason: str
    completion: Completion
    violations: tuple[str, ...] = field(default_factory=tuple)
    invented_citations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        """The whole walkthrough as prose, for search and for a plain reader."""

        return "\n\n".join(
            f"{section.heading}\n{section.text}" for section in self.sections
        )

    @property
    def word_count(self) -> int:
        return sum(len(section.text.split()) for section in self.sections)

    @property
    def valid(self) -> bool:
        return self.eligible and not self.violations and bool(self.sections)


def known_labels(structure: dict[str, Any] | None) -> frozenset[str]:
    """Every label retrieval actually recovered from the document."""

    structure = structure or {}
    labels: set[str] = set()
    for section in structure.get("sections") or []:
        title = (section or {}).get("title")
        if title:
            labels.add(str(title).strip())
    for float_ in (structure.get("figures") or []) + (structure.get("tables") or []):
        label = (float_ or {}).get("label")
        if label:
            labels.add(str(label).strip())
    return frozenset(labels)


def _matches(label: str, known: frozenset[str]) -> bool:
    """Whether a cited label names something the document has.

    Compared loosely on case and spacing, because a walkthrough that writes
    "Figure 4" for a float labelled "Figure 4:" has cited it correctly. What
    this must catch is a citation of something that is not there at all.
    """

    # A citation of the whole map line is a citation of its label.
    cited = label.split(LABEL_SEPARATOR, 1)[0]
    flat = " ".join(cited.split()).casefold().rstrip(".:")
    return any(
        flat == " ".join(candidate.split()).casefold().rstrip(".:")
        for candidate in known
    )


def validate(technical: Technical, structure: dict[str, Any] | None) -> tuple[str, ...]:
    """Check what a machine can judge about a walkthrough."""

    problems: list[str] = []
    if not technical.eligible:
        if not technical.declined_reason.strip():
            problems.append("declined without a reason")
        return tuple(problems)

    if not technical.sections:
        problems.append("eligible but produced no sections")
        return tuple(problems)

    count = technical.word_count
    if not MIN_WORDS <= count <= MAX_WORDS:
        problems.append(f"technical is {count} words")

    # Headings are the writer's to choose — a proof strategy, a cohort, a
    # fabrication process — so nothing here checks them against a vocabulary.
    # What is checked is that they still work as headings.
    headings = [section.heading.strip() for section in technical.sections]
    if any(not h for h in headings):
        problems.append("a section has no heading")
    over = [h for h in headings if len(h.split()) > MAX_HEADING_WORDS]
    if over:
        problems.append(f"heading is a sentence, not a heading: {over[0][:48]}")
    if len({h.casefold() for h in headings}) != len(headings):
        problems.append("a heading appears twice")

    if _MATH_MARKER.search(technical.text):
        problems.append("passes an unrecovered-maths marker to the reader")

    # The layer exists to be checked, so a citation that cannot be checked is
    # the one failure that matters most.
    known = known_labels(structure)
    invented = [c.label for c in technical.citations if not _matches(c.label, known)]
    if invented:
        problems.append(
            f"cites {len(invented)} label(s) the document does not have: "
            f"{', '.join(invented[:3])}"
        )
    if technical.citations and not known:
        problems.append("cites a document with no recovered structure")

    return tuple(problems)


def _labelled(item: dict[str, Any] | None) -> str:
    """A float as the writer should see it: its label and what it shows."""

    item = item or {}
    label = str(item.get("label") or "").strip()
    caption = " ".join(str(item.get("caption") or "").split())
    if not label:
        return ""
    # Long enough to say what the figure shows, short enough that twenty of
    # them do not crowd out the document itself.
    if len(caption) > 300:
        caption = caption[:297].rstrip() + "..."
    return f"{label}{LABEL_SEPARATOR}{caption}" if caption else label


def generate_technical(
    generator: Generator,
    *,
    source_name: str,
    content_type: str,
    title: str,
    full_text: str,
    structure: dict[str, Any] | None,
) -> Technical:
    """Write the walkthrough, and check every label it claims to cite."""

    structure = structure or {}
    sections = [
        str((s or {}).get("title") or "").strip()
        for s in (structure.get("sections") or [])
    ]
    # With the caption, not just the label. A walkthrough that cites "Figure 4"
    # for "the dose-response curve" was inventing that purpose from a bare
    # number, in the one layer whose whole point is that a reader can check it.
    # The captions are already stored, already in the fetched document, and cost
    # a few hundred words of prompt.
    figures = [_labelled(f) for f in (structure.get("figures") or [])]
    tables = [_labelled(t) for t in (structure.get("tables") or [])]

    completion = generator.complete(
        PROMPT.format(
            source_name=source_name,
            content_type=content_type,
            title=title,
            sections=", ".join(s for s in sections if s) or "(none recovered)",
            figures=", ".join(f for f in figures if f) or "(none recovered)",
            tables=", ".join(t for t in tables if t) or "(none recovered)",
            full_text=full_text,
        ),
        SCHEMA,
    )
    payload = completion.payload or {}

    technical = Technical(
        sections=tuple(
            TechnicalSection(
                heading=str((s or {}).get("heading") or "").strip(),
                text=unescape_newlines(str((s or {}).get("text") or "").strip()),
            )
            for s in (payload.get("sections") or [])
            if str((s or {}).get("text") or "").strip()
        ),
        citations=tuple(
            Citation(
                label=str((c or {}).get("label") or "").strip(),
                used_for=str((c or {}).get("used_for") or "").strip(),
            )
            for c in (payload.get("citations") or [])
            if str((c or {}).get("label") or "").strip()
        ),
        prerequisites=tuple(
            str(p).strip() for p in (payload.get("prerequisites") or []) if str(p).strip()
        ),
        eligible=bool(payload.get("eligible")),
        declined_reason=str(payload.get("declined_reason") or "").strip(),
        completion=completion,
    )
    if not completion.ok:
        return technical

    known = known_labels(structure)
    return Technical(
        **{
            **technical.__dict__,
            "violations": validate(technical, structure),
            "invented_citations": tuple(
                c.label for c in technical.citations if not _matches(c.label, known)
            ),
        }
    )
