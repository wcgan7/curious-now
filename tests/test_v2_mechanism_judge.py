"""The judge that decides whether an Explain explains anything.

Its value is that it works where measurement did not. Vocabulary overlap and
causal-connective density were both tried against real output and both put a
product feature list in the same range as a wildfire explainer that is
mechanism throughout — because "more detail" and "more depth" do not differ
lexically. These tests pin the parts of the judge that are ours rather than the
model's: that a claimed mechanism must be quotable, and that an unavailable
judge never costs a story its Explain.
"""

from __future__ import annotations

from typing import Any

from curious_now_v2.generation.client import Completion, Generator, Usage
from curious_now_v2.generation.judge import (
    judge_mechanism,
    quotes_the_text,
)

EXPLAIN = (
    "A fire-generated thunderstorm begins with intense heat at the fire's "
    "surface. That heat makes the air above the flames rise rapidly, carrying "
    "smoke, ash and water vapour upward. As the rising air cools, its water "
    "vapour condenses into a cloud, and if the atmosphere is unstable enough "
    "that cloud keeps building."
)


class FakeGenerator:
    """Returns one prepared payload, so the checks around it can be tested."""

    model = "test-model"

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.payload = payload

    def complete(
        self, prompt: str, schema: dict[str, Any], *, timeout: float = 900
    ) -> Completion:
        self.prompt = prompt
        return Completion(self.payload, usage=Usage())


def _judge(payload: dict[str, Any] | None) -> Any:
    generator: Generator = FakeGenerator(payload)
    return judge_mechanism(
        generator, title="A title", source_name="Example", explain=EXPLAIN
    )


def test_a_mechanism_verdict_must_point_at_the_sentence() -> None:
    """The label is an opinion; the quote is checkable, so the quote decides."""

    judgement = _judge(
        {
            "verdict": "mechanism",
            "mechanism_sentence": "As the rising air cools, its water vapour "
            "condenses into a cloud",
            "reason": "It gives the causal chain.",
        }
    )
    assert judgement.verdict == "mechanism"
    assert judgement.explains


def test_a_mechanism_claimed_without_a_quote_is_not_one() -> None:
    """Saying yes and pointing nowhere is the failure this judge exists for."""

    judgement = _judge(
        {
            "verdict": "mechanism",
            "mechanism_sentence": "",
            "reason": "It explains the process.",
        }
    )
    assert judgement.verdict == "capability_list"
    assert not judgement.explains


def test_a_quote_that_is_not_in_the_text_is_not_a_quote() -> None:
    judgement = _judge(
        {
            "verdict": "mechanism",
            "mechanism_sentence": "The model embeds a watermark in the waveform",
            "reason": "Invented from another story.",
        }
    )
    assert judgement.verdict == "capability_list"


def test_a_capability_list_withdraws_the_layer() -> None:
    judgement = _judge(
        {
            "verdict": "capability_list",
            "mechanism_sentence": "",
            "reason": "Every clause names something the product can do.",
        }
    )
    assert not judgement.explains


def test_borderline_keeps_the_layer() -> None:
    """A layer is not withdrawn on a maybe; the judge checks, it does not write."""

    judgement = _judge(
        {
            "verdict": "borderline",
            "mechanism_sentence": "",
            "reason": "Some mechanism, buried.",
        }
    )
    assert judgement.explains


def test_a_judge_that_fails_never_costs_a_story_its_explain() -> None:
    """Losing the check is a smaller harm than dropping a good layer."""

    judgement = _judge(None)
    assert judgement.verdict == "borderline"
    assert judgement.explains


def test_quoting_needs_more_than_a_fragment() -> None:
    assert quotes_the_text("As the rising air cools, its water vapour", EXPLAIN)
    assert not quotes_the_text("the", EXPLAIN)
    assert not quotes_the_text("air cools", EXPLAIN)
