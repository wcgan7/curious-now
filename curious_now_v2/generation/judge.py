"""A second reader for Explain, whose only question is whether it explains.

The writer decides for itself whether the evidence carries a mechanism, and a
writer asked to write will generally find that it does. That produced Explains
which were inventories of what something does — "it fetches information when
needed", "it filters background noise" — fluent, accurate, and telling the
reader nothing Glance had not.

Two measures were tried first and both failed on real output. Vocabulary
overlap put the worst case mid-pack, because a feature list uses plenty of
words Glance did not. Causal-connective density tied it at zero with a wildfire
explainer that is mechanism from beginning to end. Neither separates more
detail from more depth, because that difference is not lexical.

A judge does separate them: over thirteen published Explains, two independently
framed judges agreed on twelve, and both anchors came out right — the product
announcement rejected, the wildfire piece kept. It also caught one nobody had
noticed, an explainer that listed what a telescope can do without once saying
how a dish turns radio flux into data.

The judge must quote the sentence that explains how, verbatim. That is the part
worth trusting: a label is an opinion, and a quote is checkable against the text
it came from. Where a judge cannot find one sentence, there is not one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from curious_now_v2.generation.client import Completion, Generator

PROMPT_VERSION = "judge-v1"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "mechanism_sentence", "reason"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["mechanism", "capability_list", "borderline"],
        },
        "mechanism_sentence": {
            "type": "string",
            "description": "Verbatim sentence that best explains HOW; empty if none does",
        },
        "reason": {"type": "string"},
    },
}

PROMPT = """You are judging one piece of writing for Curious Now, a calm feed \
of science worth understanding.

Its "Explain" layer answers exactly one question: HOW DOES THIS WORK? It gives \
the mechanism — the steps, the reason one thing produces another — to a reader \
who already knows the field.

The failure you are looking for is an Explain that is really an inventory of \
what something does, dressed as an explanation. A product announcement is the \
usual culprit: "it fetches information when needed", "it filters background \
noise", "it follows instructions more reliably" are capabilities. They tell the \
reader WHAT, at greater length, and never WHAT MAKES IT SO. A telescope piece \
can fail the same way: "its size allows it to detect extremely weak signals" \
says what the instrument achieves, not how it achieves it.

A mechanism says why: "a fire's heat drives air upward, which cools, so its \
water vapour condenses into a cloud", or "SynthID embeds an imperceptible \
signal in the waveform, which a detector can later look for".

Read it as the field expert it was written for. Ask: having read this, can I \
say why the thing behaves as it does, or only what it does? Assume nothing \
about whether it is good or bad.

Then answer:

- verdict: "mechanism" if it explains how or why; "capability_list" if it is \
essentially a list of what the thing does or what was found, however fluent; \
"borderline" only if you genuinely cannot tell.
- mechanism_sentence: quote, VERBATIM from the text below, the single sentence \
that best explains HOW. If no sentence does, leave it empty. That emptiness is \
the most useful thing you can tell us, and inventing a quote destroys it.
- reason: one sentence.

TITLE: {title}
SOURCE: {source_name}

EXPLAIN:
{explain}
"""


@dataclass(frozen=True)
class Judgement:
    verdict: str
    mechanism_sentence: str
    reason: str
    completion: Completion

    @property
    def explains(self) -> bool:
        """Whether this Explain earns its place as a second layer.

        Borderline is kept. The judge is a check on a writer that over-claims,
        not a second author, and a layer is not withdrawn on a maybe.
        """

        return self.verdict != "capability_list"


def _flat(value: str) -> str:
    return " ".join(value.split()).casefold()


def quotes_the_text(sentence: str, explain: str) -> bool:
    """Whether the quoted sentence really came from the Explain."""

    span = " ".join(sentence.split())
    return len(span.split()) >= 4 and _flat(span) in _flat(explain)


def judge_mechanism(
    generator: Generator,
    *,
    title: str,
    source_name: str,
    explain: str,
) -> Judgement:
    """Ask whether an Explain explains, and make it show its working."""

    completion = generator.complete(
        PROMPT.format(title=title, source_name=source_name, explain=explain),
        SCHEMA,
    )
    payload = completion.payload or {}
    verdict = str(payload.get("verdict") or "").strip()
    sentence = str(payload.get("mechanism_sentence") or "").strip()
    reason = str(payload.get("reason") or "").strip()

    if not completion.ok or verdict not in {
        "mechanism",
        "capability_list",
        "borderline",
    }:
        # A judge that failed to answer must not withdraw a layer. Losing the
        # check is a smaller harm than dropping an Explain on a broken call.
        return Judgement("borderline", sentence, reason or "judge unavailable",
                         completion)

    if verdict == "mechanism" and not quotes_the_text(sentence, explain):
        # It said yes and could not point at where. The label is an opinion;
        # the quote is the part that can be checked, so the quote decides.
        return Judgement(
            "capability_list",
            "",
            "claimed a mechanism but quoted no sentence from the text",
            completion,
        )

    return Judgement(verdict, sentence, reason, completion)


# Recorded on the explanation row so a withdrawn layer can be explained later.
DECLINED = re.compile(r"^judged a capability list")


def declined_reason(judgement: Judgement) -> str:
    return f"judged a capability list rather than a mechanism: {judgement.reason}"
