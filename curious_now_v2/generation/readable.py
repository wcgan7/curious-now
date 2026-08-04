"""A second reader for the Glance, whose only question is whether it lands.

Every other rung is guarded. Technical is checked against the document: a cited
figure must exist. Explain has a judge that must quote the sentence explaining
how, because two lexical measures were tried first and both failed on real
output. The Glance -- the rung the whole product rests on -- was checked for
word count and for a qualification quoted verbatim, and nothing else.

The prompt already asks for the right thing, in plain terms: "for someone
curious with no background in this field -- imagine a sharp friend who works in
something else", and "a Glance that reads like a compressed abstract has failed
even if every word in it is true". An instruction nothing enforces drifts.
Reviewed over 140 published stories, 9% of Glances needed the field to read and
11% opened by referring to something the reader had never met -- "The key idea
is to stabilize the algorithm", where no algorithm had been mentioned.

The judge takes the same shape as the Explain one, for the same reason: a
verdict on its own is an opinion that does not calibrate between calls, and a
verbatim quote can be checked against the text it came from. Where the judge
says a Glance needs the field, it must point at the phrase that blocked it, in
the writer's own words. In the review that produced this, 58 of 60 quotes were
found verbatim in our text.

What it deliberately does not judge: whether the science is interesting, or
whether the Glance is complete. A Glance can be true, thorough and unreadable,
and that is the only failure this looks for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from curious_now_v2.generation.client import Completion, Generator

PROMPT_VERSION = "readable-v1"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    # Every property, not only the interesting ones: strict structured output
    # rejects a schema whose `properties` and `required` differ, and reports it
    # as empty output rather than as a schema error.
    "required": ["verdict", "blocking_phrase", "reason"],
    "properties": {
        "verdict": {"type": "string", "enum": ["plain", "needs_the_field"]},
        "blocking_phrase": {"type": "string"},
        "reason": {"type": "string"},
    },
}

PROMPT = """You are scientifically literate with no background in this \
particular field. You did a science degree a while ago, you read widely, and \
you work in something else entirely.

Read the explanation below and answer one question: can you follow it?

verdict
  plain            you finish it knowing one thing you did not know before,
                   and you could tell a friend what it was
  needs_the_field  you would have to already work in this area

blocking_phrase
  If it needs the field, the single phrase that most blocks you, quoted \
VERBATIM from the explanation. Copy it exactly; do not paraphrase it. Empty \
string only when the verdict is plain.

reason
  One short sentence. What stopped you, or what let you through.

Two things block a reader most often, and both count:

  - a term used without being explained where it appears
  - a reference to something as though you had already met it: "the algorithm",
    "this method", "the model" -- when nothing before it said what that was

Judge only whether you can read it. An explanation can be entirely true, and \
carefully qualified, and still tell you nothing — that is exactly what this is \
looking for.

TITLE: {title}

EXPLANATION:
{glance}
"""


@dataclass(frozen=True)
class Readability:
    verdict: str
    blocking_phrase: str
    reason: str
    completion: Completion

    @property
    def plain(self) -> bool:
        return self.verdict == "plain"


def _flat(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def quotes_the_glance(phrase: str, glance: str) -> bool:
    """Whether the blocking phrase really appears in what the reader reads.

    A judge that cannot point at the words is guessing, and a phrase it
    invented would send the writer to fix something it never wrote.
    """

    flat = _flat(phrase)
    return bool(flat) and flat in _flat(glance)


def judge_readability(
    generator: Generator, *, title: str, glance: str
) -> Readability:
    """Whether a curious non-expert can read this Glance.

    A verdict of `needs_the_field` without a quote from the Glance is demoted
    to `plain`: the judge has failed to show its work, and refusing a Glance on
    an unevidenced opinion is worse than letting one through. That mirrors the
    significance judge, where a `changes_practice` without its quote is demoted
    rather than trusted.
    """

    completion = generator.complete(
        PROMPT.format(title=title or "", glance=glance or ""), SCHEMA
    )
    payload = completion.payload or {}
    verdict = str(payload.get("verdict") or "").strip()
    phrase = str(payload.get("blocking_phrase") or "").strip()
    reason = str(payload.get("reason") or "").strip()

    if verdict != "needs_the_field":
        return Readability("plain", "", reason, completion)
    if not quotes_the_glance(phrase, glance):
        return Readability(
            "plain",
            "",
            reason or "judge named no phrase from the glance",
            completion,
        )
    return Readability("needs_the_field", phrase, reason, completion)
