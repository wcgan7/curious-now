from __future__ import annotations

from dataclasses import dataclass

from curious_now_v2.retrieval.document import Document, SectionKind

# Weights sum to 1.0, so a score reads directly as a fraction of what a well
# extracted paper would offer.
WEIGHT_LENGTH = 0.40
WEIGHT_STRUCTURE = 0.25
WEIGHT_ROLES = 0.20
WEIGHT_FLOATS = 0.15

# Beyond this a document has all the text an explanation can use.
SATURATION_WORDS = 6000
SATURATION_FLOATS = 8

# The roles that make a document worth going deep on.
KEY_ROLES = (
    SectionKind.METHOD,
    SectionKind.RESULTS,
    (SectionKind.LIMITATIONS, SectionKind.DISCUSSION),
)

# A tie between candidates goes to the source that needed least inference.
# Markup states its structure; a PDF's is reconstructed from geometry.
SOURCE_BONUS = {
    "arxiv_html": 0.06,
    "pmc_jats": 0.06,
    "publisher_html": 0.02,
    "article_html": 0.02,
    "oa_pdf": 0.0,
    "arxiv_pdf": 0.0,
}

# Once a candidate scores this well, later ones cannot realistically beat it,
# so the remaining fetches are skipped. This is a politeness measure as much as
# a performance one: it avoids pulling a PDF we will not use.
GOOD_ENOUGH = 0.70


@dataclass(frozen=True)
class ScoredDocument:
    document: Document
    source: str
    score: float
    reasons: tuple[str, ...]


def score_document(document: Document, *, source: str = "") -> ScoredDocument:
    """Rate one extraction so several copies of the same item can be compared.

    The score ranks candidates against each other; it is not a quality measure
    across item kinds. A news article scores far below a paper because it has
    no sections or figures to offer, which says nothing about the article.
    Whether text is good enough to publish is decided by `assess_text`.
    """

    words = document.word_count
    length = min(words / SATURATION_WORDS, 1.0)

    structure = 1.0 if document.has_structure else 0.0

    present = 0
    for role in KEY_ROLES:
        wanted = role if isinstance(role, tuple) else (role,)
        if document.sections_of_kind(*wanted):
            present += 1
    roles = present / len(KEY_ROLES)

    floats = min(
        (len(document.figures) + len(document.tables)) / SATURATION_FLOATS, 1.0
    )

    score = (
        WEIGHT_LENGTH * length
        + WEIGHT_STRUCTURE * structure
        + WEIGHT_ROLES * roles
        + WEIGHT_FLOATS * floats
    )
    score = max(0.0, min(1.0, score + SOURCE_BONUS.get(source, 0.0)))
    if document.warnings:
        score *= 0.5

    reasons: list[str] = [
        f"{words} words",
        "sections classified" if structure else "no section structure",
        f"{present}/{len(KEY_ROLES)} key roles present",
        f"{len(document.figures) + len(document.tables)} citable floats",
    ]
    if document.warnings:
        reasons.append(f"halved for: {'; '.join(document.warnings)}")

    return ScoredDocument(
        document=document,
        source=source,
        score=round(score, 4),
        reasons=tuple(reasons),
    )


def pick_best(
    scored: tuple[ScoredDocument, ...],
) -> ScoredDocument | None:
    """Choose the richest extraction, breaking ties toward structured sources."""

    usable = [entry for entry in scored if entry.document.word_count > 0]
    if not usable:
        return None
    return max(
        usable,
        key=lambda entry: (entry.score, SOURCE_BONUS.get(entry.source, 0.0)),
    )


def is_good_enough(scored: ScoredDocument) -> bool:
    """Whether to stop fetching further candidates for this item."""

    return scored.score >= GOOD_ENOUGH
