from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from curious_now_v2.core.enums import ExplanationDepth

# Word budgets, derived from what the presentation contract asks each layer to
# do. Glance is ~30-60 seconds; Explain is 3-6 minutes and must cover mechanism,
# evidence, comparison, and limitations; Technical walks through the work.
# Source text must comfortably exceed the output it grounds.
MIN_WORDS_ANY = 150
MIN_WORDS_EXPLAIN = 600
MIN_WORDS_TECHNICAL = 2000

# Publishers serve a teaser plus a subscription pitch under HTTP 200, and each
# words it differently ("exclusive to STAT+ subscribers", "Access options" plus
# a Nature+ price). Match the shape of the offer rather than exact phrases.
PAYWALL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.I))
    for label, pattern in (
        ("access options", r"\baccess options\b"),
        ("subscriber-only article", r"\b(?:exclusive to|only for|reserved for)\b[^.\n]{0,40}\bsubscribers?\b"),
        ("subscriber-only article", r"\bthis (?:article|story|content) is (?:for|exclusive to)\b"),
        ("unlock prompt", r"\bunlock (?:this|the|full)\b"),
        ("subscribe prompt", r"\bsubscribe (?:now|today|to continue|for)\b"),
        ("continue-reading gate", r"\bto continue reading\b|\bcontinue reading (?:with|for)\b"),
        ("existing-account prompt", r"\balready (?:have an account|a subscriber|subscribed)\b"),
        ("sign-in gate", r"\b(?:sign|log) in to (?:continue|read|view)\b"),
        ("purchase offer", r"\b(?:buy this article|purchase access|rent or buy)\b"),
        ("institutional offer", r"\binstitutional subscriptions?\b"),
        ("registration gate", r"\b(?:create your free account|register to (?:read|continue))\b"),
    )
)

_PRICE_PATTERN = re.compile(
    r"(?:[$£€]\s?\d+[.,]?\d*|\d+[.,]\d{2}\s?[$£€])\s*/?\s*"
    r"(?:per\s+)?(?:30\s+days|month|year|issue)",
    re.I,
)

ACADEMIC_SECTIONS = (
    "introduction",
    "background",
    "related work",
    "method",
    "materials",
    "results",
    "discussion",
    "conclusion",
    "references",
)


class TextVerdict(StrEnum):
    USABLE = "usable"
    TOO_SHORT = "too_short"
    SOFT_PAYWALL = "soft_paywall"


@dataclass(frozen=True)
class TextAssessment:
    """Whether extracted text can ground a presentation, and how deep."""

    verdict: TextVerdict
    words: int
    section_hits: int
    supported_depths: tuple[ExplanationDepth, ...]
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def usable(self) -> bool:
        return self.verdict is TextVerdict.USABLE


def _paywall_signals(text: str) -> tuple[tuple[str, float], ...]:
    """Paywall markers with where each sits in the document, 0.0 to 1.0."""

    if not text:
        return ()
    found: dict[str, float] = {}
    for label, pattern in PAYWALL_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            position = matches[-1].start() / len(text)
            found[label] = max(found.get(label, 0.0), position)
    # A subscription price only matters alongside offer language, since
    # articles about commerce legitimately quote prices.
    if found:
        price = _PRICE_PATTERN.search(text)
        if price:
            found["subscription price"] = price.start() / len(text)
    return tuple(found.items())


def count_section_hits(text: str) -> int:
    lowered = text.casefold()
    return sum(1 for section in ACADEMIC_SECTIONS if section in lowered)


def assess_text(text: str, *, has_structure: bool = False) -> TextAssessment:
    """Judge extracted text before it is allowed to ground an explanation.

    `has_structure` marks text from a source that carries real section markup
    (arXiv LaTeXML, JATS), which is what Technical needs in order to cite
    sections, figures, and tables.
    """

    stripped = text.strip()
    words = len(stripped.split())
    sections = count_section_hits(stripped)
    signals = _paywall_signals(stripped)

    if signals:
        # A teaser is short and puts the offer at the end. A long article that
        # merely mentions subscriptions in passing is not a paywall.
        trailing = any(
            position > 0.5 for label, position in signals if label != "subscription price"
        )
        if words < MIN_WORDS_EXPLAIN or (trailing and len(signals) >= 2):
            labels = [label for label, _ in signals]
            return TextAssessment(
                verdict=TextVerdict.SOFT_PAYWALL,
                words=words,
                section_hits=sections,
                supported_depths=(),
                reasons=(
                    f"subscription markers present: {', '.join(labels[:3])}",
                    f"only {words} words of body text",
                ),
            )

    if words < MIN_WORDS_ANY:
        return TextAssessment(
            verdict=TextVerdict.TOO_SHORT,
            words=words,
            section_hits=sections,
            supported_depths=(),
            reasons=(f"{words} words is below the {MIN_WORDS_ANY}-word floor",),
        )

    depths = [ExplanationDepth.GLANCE]
    reasons = [f"{words} words of usable text"]
    if words >= MIN_WORDS_EXPLAIN:
        depths.append(ExplanationDepth.EXPLAIN)
    else:
        reasons.append(
            f"below {MIN_WORDS_EXPLAIN} words; too thin for a field-aware Explain"
        )

    if words >= MIN_WORDS_TECHNICAL and has_structure and sections >= 3:
        depths.append(ExplanationDepth.TECHNICAL)
    elif words >= MIN_WORDS_TECHNICAL and not has_structure:
        reasons.append("no section structure to cite for Technical")

    return TextAssessment(
        verdict=TextVerdict.USABLE,
        words=words,
        section_hits=sections,
        supported_depths=tuple(depths),
        reasons=tuple(reasons),
    )
