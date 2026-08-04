"""The Glance judge, and the ways a judge can be wrong.

What it protects is the rung the product rests on: an explanation for someone
with no background in the field. What it must not do is refuse one on an
opinion, which is why every rejection has to carry a phrase from the writer's
own text.
"""

from __future__ import annotations

from typing import Any

from curious_now_v2.generation.client import Completion, Usage
from curious_now_v2.generation.readable import (
    SCHEMA,
    judge_readability,
    quotes_the_glance,
)

GLANCE = (
    "A model predicts protein shapes from their sequence alone, which used to "
    "take months of laboratory work. It matters because knowing a shape is "
    "most of knowing what a protein does."
)


class FakeGenerator:
    model = "test"

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, schema: dict[str, Any], **_: Any) -> Completion:
        self.prompts.append(prompt)
        return Completion(self.payload, usage=Usage())


def test_a_plain_glance_passes_and_carries_no_phrase() -> None:
    judged = judge_readability(
        FakeGenerator({"verdict": "plain", "blocking_phrase": "", "reason": "clear"}),
        title="Predicting protein shape",
        glance=GLANCE,
    )
    assert judged.plain
    assert judged.blocking_phrase == ""


def test_a_rejection_must_point_at_the_writers_own_words() -> None:
    judged = judge_readability(
        FakeGenerator(
            {
                "verdict": "needs_the_field",
                "blocking_phrase": "knowing a shape is most of knowing",
                "reason": "assumes structural biology",
            }
        ),
        title="t",
        glance=GLANCE,
    )
    assert not judged.plain
    assert judged.blocking_phrase in GLANCE


def test_a_rejection_with_an_invented_phrase_is_not_a_rejection() -> None:
    """A judge that cannot show the words is guessing.

    Letting one hard Glance through is a smaller harm than refusing a good one
    on an opinion, and would send the writer to fix a phrase it never wrote.
    """

    judged = judge_readability(
        FakeGenerator(
            {
                "verdict": "needs_the_field",
                "blocking_phrase": "stochastic variational inference",
                "reason": "too technical",
            }
        ),
        title="t",
        glance=GLANCE,
    )
    assert judged.plain
    assert judged.blocking_phrase == ""
    assert judged.reason


def test_a_rejection_with_no_phrase_at_all_is_not_a_rejection() -> None:
    judged = judge_readability(
        FakeGenerator(
            {"verdict": "needs_the_field", "blocking_phrase": "", "reason": "hard"}
        ),
        title="t",
        glance=GLANCE,
    )
    assert judged.plain


def test_an_unusable_reply_does_not_reject_the_glance() -> None:
    """A failed call must not silently withhold a rung a reader could have had."""

    assert judge_readability(FakeGenerator(None), title="t", glance=GLANCE).plain


def test_an_unknown_verdict_is_read_as_plain_rather_than_as_a_refusal() -> None:
    judged = judge_readability(
        FakeGenerator(
            {"verdict": "maybe", "blocking_phrase": "protein", "reason": "unsure"}
        ),
        title="t",
        glance=GLANCE,
    )
    assert judged.plain


def test_the_judge_reads_the_glance_not_the_source() -> None:
    """It judges what the reader sees. Handing it the source text would let a
    term be 'explained' somewhere the reader never goes."""

    generator = FakeGenerator({"verdict": "plain", "blocking_phrase": "", "reason": ""})
    judge_readability(generator, title="A title", glance=GLANCE)
    prompt = generator.prompts[0]
    assert GLANCE in prompt
    assert "A title" in prompt


def test_quotes_the_glance_ignores_how_the_text_was_wrapped() -> None:
    assert quotes_the_glance("used to take months", "...which\nused  to take\nmonths...")
    assert quotes_the_glance("USED TO TAKE MONTHS", "which used to take months")
    assert not quotes_the_glance("", GLANCE)
    assert not quotes_the_glance("never written", GLANCE)


def test_the_schema_requires_every_property_it_declares() -> None:
    """Strict structured output rejects a schema whose `properties` and
    `required` differ, and reports it as empty output rather than as a schema
    error -- which cost an afternoon once already."""

    assert set(SCHEMA["required"]) == set(SCHEMA["properties"])
