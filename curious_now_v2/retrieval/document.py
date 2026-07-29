from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import StrEnum


class SectionKind(StrEnum):
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    RELATED_WORK = "related_work"
    METHOD = "method"
    RESULTS = "results"
    DISCUSSION = "discussion"
    LIMITATIONS = "limitations"
    CONCLUSION = "conclusion"
    APPENDIX = "appendix"
    REFERENCES = "references"
    ACKNOWLEDGEMENTS = "acknowledgements"
    OTHER = "other"


# Ordered most specific first: "related work" must not be read as "work", and
# "results and discussion" must not be claimed by the discussion rule.
# Romance-language equivalents are included because PubMed Central carries a
# large body of Spanish- and Portuguese-language research. Without them every
# heading falls through to OTHER, which costs the article its structure and so
# its eligibility for the deeper layers.
_SECTION_PATTERNS: tuple[tuple[SectionKind, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.I))
    for kind, pattern in (
        (SectionKind.ABSTRACT, r"^\s*(abstract|resumo|resumen|résumé)\b"),
        (
            SectionKind.REFERENCES,
            r"^\s*(references|bibliography|works cited"
            r"|referências|referencias|références|bibliografía)\b",
        ),
        (
            SectionKind.ACKNOWLEDGEMENTS,
            r"^\s*(acknowledg|agradecimento|agradecimiento|remerciement)",
        ),
        (
            SectionKind.LIMITATIONS,
            r"\b(limitations?|threats to validity|limitaç|limitacion)\w*",
        ),
        (
            SectionKind.RELATED_WORK,
            r"\b(related work|prior work|previous work|literature review"
            r"|trabalhos relacionados|trabajos relacionados)\b",
        ),
        (
            SectionKind.METHOD,
            # method\w* so "Methodology" and "Methods" both land here. Proofs,
            # derivations, and constructions are the mechanism in a theory
            # paper, where nothing is ever called a method.
            r"\b(method\w*|materia\w*|approach|architecture|"
            r"model design|implementation|experimental\s+(setup|design|procedure)|"
            r"proofs?|derivations?|constructions?|algorithms?"
            r"|m[ée]todo\w*|metodolog\w*|m[ée]thode\w*|procedimento\w*)\b",
        ),
        (
            SectionKind.RESULTS,
            r"\b(results?|findings|evaluation|experiments?"
            r"|resultados?|résultats?|achados)\b",
        ),
        (SectionKind.DISCUSSION, r"\b(discussion|discussão|discusión)\b"),
        (
            SectionKind.CONCLUSION,
            r"\b(conclusions?|concluding|future work|outlook"
            r"|conclus[õoóa]\w*|considerações finais)\b",
        ),
        (
            SectionKind.INTRODUCTION,
            # "Contexto" is deliberately absent: under a methods heading it
            # means the study setting, not background.
            r"\b(introduction|background|motivation"
            r"|introdu[çc]\w*|introducci[óo]n|antecedentes)\b",
        ),
    )
)

# Numbered headings arrive as "3 Methodology" or "3.1. Preliminaries".
_LEADING_NUMBER = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")


def classify_section(title: str | None) -> SectionKind:
    """Map a heading to the role it plays in a paper."""

    if not title:
        return SectionKind.OTHER
    cleaned = _LEADING_NUMBER.sub("", title).strip()
    for kind, pattern in _SECTION_PATTERNS:
        if pattern.search(cleaned):
            return kind
    return SectionKind.OTHER


@dataclass(frozen=True)
class Figure:
    """A figure's caption. The image itself is not stored; the caption is what
    an explanation can cite and a reader can be pointed at."""

    label: str | None
    caption: str


@dataclass(frozen=True)
class Table:
    label: str | None
    caption: str | None
    body: str = ""


@dataclass(frozen=True)
class Section:
    title: str | None
    kind: SectionKind
    paragraphs: tuple[str, ...] = ()
    level: int = 1

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def word_count(self) -> int:
        return sum(len(paragraph.split()) for paragraph in self.paragraphs)


_PRE_METHOD = frozenset({SectionKind.INTRODUCTION, SectionKind.RELATED_WORK})
_POST_METHOD = frozenset(
    {
        SectionKind.RESULTS,
        SectionKind.DISCUSSION,
        SectionKind.CONCLUSION,
        SectionKind.LIMITATIONS,
    }
)
# Back matter, never body content in its own right.
_TRAILING = frozenset(
    {
        SectionKind.APPENDIX,
        SectionKind.REFERENCES,
        SectionKind.ACKNOWLEDGEMENTS,
    }
)


def infer_method_sections(sections: tuple[Section, ...]) -> tuple[Section, ...]:
    """Treat unlabelled sections between the introduction and the results as
    method content.

    Papers routinely name the methods section after the method itself —
    "Probabilistic Surrogate for RAMBO", "Acquisition Functions" — so no
    keyword matches. Position is the reliable signal: whatever sits between the
    background and the experiments is where the work is described.

    This infers a contribution zone rather than a precise methods section. When
    a paper labels no results section, the zone runs to the conclusion and will
    include result-bearing prose. That is the intended trade: a coarse
    mechanism signal beats none, and claim extraction reads the text either way.
    """

    top_level = [
        (index, section)
        for index, section in enumerate(sections)
        if section.level == 1
    ]
    start = next(
        (index for index, section in top_level if section.kind in _PRE_METHOD),
        None,
    )
    if start is None:
        return sections
    # A theory paper often has no results or conclusion section at all, so fall
    # back to the start of the back matter, then to the end of the document.
    end = next(
        (
            index
            for index, section in top_level
            if index > start and section.kind in _POST_METHOD
        ),
        None,
    )
    if end is None:
        end = next(
            (
                index
                for index, section in top_level
                if index > start and section.kind in _TRAILING
            ),
            len(sections),
        )

    return tuple(
        replace(section, kind=SectionKind.METHOD)
        if (
            start < index < end
            and section.level == 1
            and section.kind is SectionKind.OTHER
        )
        else section
        for index, section in enumerate(sections)
    )


def inherit_section_kinds(sections: tuple[Section, ...]) -> tuple[Section, ...]:
    """Give an unclassified subsection the role of the section containing it.

    "Statistical analyses" under "Materials and methods", or "Preliminaries"
    under "Methodology", are method content even though their own headings say
    nothing about method. Inheriting from the enclosing section keeps them
    attributed to the right role.
    """

    resolved: list[Section] = []
    ancestors: dict[int, SectionKind] = {}
    for section in sections:
        for level in [key for key in ancestors if key >= section.level]:
            del ancestors[level]

        kind = section.kind
        if kind is SectionKind.OTHER and ancestors:
            kind = ancestors[max(ancestors)]
        if kind is not SectionKind.OTHER:
            ancestors[section.level] = kind
        resolved.append(
            section if kind is section.kind else replace(section, kind=kind)
        )
    return tuple(resolved)


@dataclass(frozen=True)
class Document:
    """Extracted text with the structure an explanation needs to cite.

    Section, figure, and table structure is preserved rather than flattened,
    because Technical is required to cite the sections, figures, and tables it
    draws on, and layer eligibility depends on whether a method section exists
    at all.
    """

    extraction_method: str
    title: str | None = None
    abstract: str | None = None
    sections: tuple[Section, ...] = ()
    figures: tuple[Figure, ...] = ()
    tables: tuple[Table, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def body_text(self) -> str:
        """Section prose, excluding references and acknowledgements."""

        return "\n\n".join(
            part
            for section in self.sections
            if section.kind
            not in {SectionKind.REFERENCES, SectionKind.ACKNOWLEDGEMENTS}
            for part in ((section.title or "").strip(), section.text)
            if part
        )

    @property
    def text(self) -> str:
        """Everything an explanation may draw on, captions included."""

        parts = [self.title or "", self.abstract or "", self.body_text]
        parts.extend(
            f"{figure.label + ': ' if figure.label else ''}{figure.caption}"
            for figure in self.figures
        )
        parts.extend(
            f"{table.label or ''} {table.caption or ''} {table.body}".strip()
            for table in self.tables
        )
        return "\n\n".join(part for part in parts if part.strip())

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def has_structure(self) -> bool:
        """Whether real sections were recovered, not just a wall of prose."""

        return any(
            section.kind is not SectionKind.OTHER for section in self.sections
        )

    def sections_of_kind(self, *kinds: SectionKind) -> tuple[Section, ...]:
        wanted = set(kinds)
        return tuple(
            section for section in self.sections if section.kind in wanted
        )

    @property
    def has_method_section(self) -> bool:
        """Whether the document describes its own methodology.

        This is a signal for packet construction, not Explain's eligibility
        gate. A review or editorial explains mechanisms at length while having
        no methods section of its own, so mechanism support is decided from the
        claims a packet actually carries, not from this property.
        """

        return bool(self.sections_of_kind(SectionKind.METHOD))
