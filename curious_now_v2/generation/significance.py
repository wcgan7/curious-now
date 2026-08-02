"""Whether a result would change what someone in the field does next.

Ranking needs a signal about the science, and the only ones available free were
how many rungs a story earned -- three levels -- and a set of measures that
turned out to separate nothing: 165 of 168 packets carry a result claim, and
claim counts track how long the document was.

The obvious remedy is to ask the model, and the obvious form of the question is
the wrong one. A scalar rating does not calibrate: an eight from one call means
nothing against an eight from another, because each call sees one story and no
corpus. This codebase already learned the general shape of that lesson when the
Explain writer was left to decide whether it had explained -- two metrics were
tried against real output and both failed, and a judge required to quote
verbatim agreed with an independently framed second judge on twelve of thirteen.

So this is a judge, not a rater. One question, three answers, and a quotation
that can be checked against the evidence the packet already grounded in the
source. The quote is the part worth trusting: a verdict is an opinion, and an
excerpt is checkable against the document it came from.

It reads the packet's claims rather than the paper. Those are already extracted
and already backed by verbatim excerpts, which makes the input a few hundred
words instead of thirty thousand, and makes the answer checkable against
something we have rather than something we would have to re-fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from curious_now_v2.generation.client import Completion, Generator

PROMPT_VERSION = "significance-v1"

VERDICTS = ("changes_practice", "incremental", "unclear")

# How many claims to show. Enough to represent a paper, few enough that the
# judge reads them all rather than skimming a wall.
MAX_CLAIMS = 26
EXCERPT_CHARS = 300
MIN_QUOTE_WORDS = 5

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "quote", "reason"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "quote": {
            "type": "string",
            "description": (
                "Verbatim excerpt, copied from the evidence below, that "
                "establishes the verdict; empty if none does"
            ),
        },
        "reason": {"type": "string"},
    },
}

PROMPT = """You are judging one piece of research for Curious Now, a calm feed \
of science worth understanding.

One question: WOULD THIS CHANGE WHAT SOMEONE WORKING IN THIS FIELD DOES NEXT?

Answer as a working member of that field, reading this alongside everything \
else published that week.

- changes_practice: someone would do something differently having read it. A \
method that measurably beats what people use. A finding that overturns an \
assumption the field was relying on. A tool or dataset people would adopt. A \
result that closes off a line of work.
- incremental: a real contribution that extends the existing line without \
redirecting it. Better numbers on a known benchmark, one more species \
surveyed, a variation on an established method. Most good research is this, \
and calling it so is not an insult.
- unclear: you genuinely cannot tell from the evidence given.

What this question is NOT:

1. NOT how confident the writing is. Papers overclaim in abstracts, and \
"paradigm-shifting" and "unprecedented" are marketing. Judge the result.
2. NOT how large the effect is. A precise null result that closes a promising \
avenue changes practice. A large effect nobody can act on does not.
3. NOT how interesting it is to a general reader. That is a different question \
and this feed answers it elsewhere.
4. NOT whether the work is competent. Almost all of it is.

Then answer:

- verdict: one of the three above.
- quote: copy, VERBATIM, the single excerpt below that best establishes your \
verdict. It must appear in the evidence exactly as written. If nothing does, \
leave it empty — that emptiness is more useful than an invented quote, and \
inventing one destroys the only part of this that can be checked.
- reason: one sentence, naming what would be done differently, or why nothing \
would be.

TITLE: {title}
SOURCE: {source_name}

EVIDENCE:
{evidence}
"""


@dataclass(frozen=True)
class CandidateClaim:
    claim_kind: str
    claim_text: str
    excerpt: str


@dataclass(frozen=True)
class Significance:
    verdict: str
    quote: str
    reason: str
    completion: Completion

    @property
    def changes_practice(self) -> bool:
        return self.verdict == "changes_practice"


def _flat(value: str) -> str:
    return " ".join(value.split()).casefold()


def quotes_the_evidence(quote: str, claims: list[CandidateClaim]) -> bool:
    """Whether the quoted span really came from the evidence shown.

    Checked against the excerpts, which the packet already grounded verbatim in
    the source, so a passing quote is traceable to the document itself.
    """

    span = " ".join(quote.split())
    if len(span.split()) < MIN_QUOTE_WORDS:
        return False
    needle = _flat(span)
    return any(needle in _flat(claim.excerpt) for claim in claims)


def render_evidence(claims: list[CandidateClaim]) -> str:
    return "\n".join(
        f"[{claim.claim_kind}] {claim.claim_text}\n"
        f'    "{claim.excerpt[:EXCERPT_CHARS]}"'
        for claim in claims[:MAX_CLAIMS]
    )


def judge_significance(
    generator: Generator,
    *,
    title: str,
    source_name: str,
    claims: list[CandidateClaim],
) -> Significance:
    """Ask whether a result would change practice, and make it show where."""

    usable = [claim for claim in claims if claim.excerpt.strip()]
    if not usable:
        # Nothing grounded to judge against. Not a failure of the paper.
        return Significance(
            "unclear", "", "no grounded evidence to judge",
            Completion(payload=None, error="no evidence"),
        )

    completion = generator.complete(
        PROMPT.format(
            title=title,
            source_name=source_name,
            evidence=render_evidence(usable),
        ),
        SCHEMA,
    )
    payload = completion.payload or {}
    verdict = str(payload.get("verdict") or "").strip()
    quote = str(payload.get("quote") or "").strip()
    reason = str(payload.get("reason") or "").strip()

    if not completion.ok or verdict not in VERDICTS:
        # A judge that could not answer must not push a story down. Losing the
        # signal is a smaller harm than inventing a verdict from a broken call.
        return Significance(
            "unclear", quote, reason or "judge unavailable", completion
        )

    if verdict == "changes_practice" and not quotes_the_evidence(quote, usable):
        # It made the strongest claim available and could not point at where.
        # The verdict is an opinion; the quote is checkable, so the quote wins.
        return Significance(
            "incremental",
            "",
            "claimed a practice change but quoted nothing from the evidence",
            completion,
        )

    return Significance(verdict, quote, reason, completion)
