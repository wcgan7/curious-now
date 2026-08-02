from __future__ import annotations

from typing import Any

import pytest

from curious_now_v2.generation.citations import (
    MAX_SHOWN,
    MAX_TYPED,
    CitedWork,
    render_references,
    selected,
    type_citations,
)
from curious_now_v2.generation.client import Completion


class FakeGenerator:
    """Returns a canned payload and records the prompt it was given."""

    model = "test"

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(
        self, prompt: str, schema: dict[str, Any], *, timeout: float = 900
    ) -> Completion:
        self.prompts.append(prompt)
        return Completion(payload=self.payload)


def work(
    key: str = "bib1",
    *,
    mentions: int = 1,
    contexts: tuple[str, ...] = ("We adopt the estimator of Smith et al. [1].",),
    text: str = "Smith, J. An estimator for things. Journal 1, 1 (2020).",
    sections: tuple[str, ...] = ("method",),
) -> CitedWork:
    return CitedWork(
        ref_key=key,
        label=key[-1],
        citation_text=text,
        doi=None,
        arxiv_id=None,
        mentions=mentions,
        cited_sections=sections,
        contexts=contexts,
    )


def payload(**overrides: Any) -> dict[str, Any]:
    edge = {
        "ref": "1",
        "relation": "applies",
        "quote": "We adopt the estimator of Smith et al.",
        "reason": "uses its estimator",
    }
    edge.update(overrides)
    return {"edges": [edge]}


# --- grounding --------------------------------------------------------------


def test_a_well_evidenced_edge_is_kept() -> None:
    result = type_citations(FakeGenerator(payload()), title="T", works=[work()])

    assert [edge.relation for edge in result.edges] == ["applies"]
    assert result.edges[0].ref_key == "bib1"


def test_a_quote_absent_from_the_citing_text_is_rejected() -> None:
    """The whole check: a relation must point at where the paper said it.

    Without this the model is asserting a relationship to a paper it has not
    read, attached to a reference it picked freely.
    """

    result = type_citations(
        FakeGenerator(payload(quote="We reproduce the findings of Smith et al.")),
        title="T",
        works=[work()],
    )

    assert result.edges == ()
    assert any("not in this reference" in reason for reason in result.rejected)


def test_a_reference_that_does_not_exist_is_rejected() -> None:
    result = type_citations(
        FakeGenerator(payload(ref="9")), title="T", works=[work()]
    )

    assert result.edges == ()
    assert any("no such reference" in reason for reason in result.rejected)


def test_a_relation_outside_the_vocabulary_is_rejected() -> None:
    """paper_relations constrains these, so an invalid one would fail on write."""

    result = type_citations(
        FakeGenerator(payload(relation="inspired_by")), title="T", works=[work()]
    )

    assert result.edges == ()
    assert any("not allowed" in reason for reason in result.rejected)


def test_cites_is_never_emitted() -> None:
    """Background is the default; an edge should say more than "a citation"."""

    result = type_citations(
        FakeGenerator(payload(relation="cites")), title="T", works=[work()]
    )

    assert result.edges == ()


def test_a_quote_too_short_to_check_is_rejected() -> None:
    result = type_citations(
        FakeGenerator(payload(quote="We adopt")), title="T", works=[work()]
    )

    assert result.edges == ()


def test_the_same_reference_is_not_typed_twice() -> None:
    generator = FakeGenerator(
        {
            "edges": [
                payload()["edges"][0],
                payload(relation="extends")["edges"][0],
            ]
        }
    )
    result = type_citations(generator, title="T", works=[work()])

    assert len(result.edges) == 1


def test_the_number_of_edges_is_capped() -> None:
    works = [
        work(f"bib{index}", contexts=(f"We adopt the method of ref {index} here.",))
        for index in range(1, MAX_TYPED + 6)
    ]
    edges = [
        {
            "ref": str(index),
            "relation": "applies",
            "quote": f"We adopt the method of ref {index} here.",
            "reason": "x",
        }
        for index in range(1, len(works) + 1)
    ]
    result = type_citations(
        FakeGenerator({"edges": edges}), title="T", works=works
    )

    assert len(result.edges) == MAX_TYPED


# --- what the model is shown ------------------------------------------------


def test_references_with_no_in_text_citation_are_not_sent() -> None:
    """A reference the body never cites has no sentence to ground anything."""

    generator = FakeGenerator({"edges": []})
    type_citations(
        generator,
        title="T",
        works=[work("bib1"), work("bib2", contexts=())],
    )

    assert "bib2" not in generator.prompts[0]
    assert generator.prompts[0].count("cited 1x") == 1


def test_nothing_is_sent_when_no_reference_was_cited() -> None:
    """Declining before the call costs nothing; calling anyway costs money."""

    generator = FakeGenerator(payload())
    result = type_citations(
        generator, title="T", works=[work("bib1", contexts=())]
    )

    assert generator.prompts == []
    assert result.edges == ()
    assert result.completion.error == "no citation contexts"


def test_a_long_bibliography_is_trimmed_and_says_so() -> None:
    """Silent truncation reads as full coverage when it is not."""

    works = [work(f"bib{index}", mentions=index) for index in range(MAX_SHOWN + 30)]
    shown, dropped = selected(works)

    assert len(shown) == MAX_SHOWN
    assert dropped == 30
    # Trimmed by mention count, so the least cited go first.
    assert min(entry.mentions for entry in shown) > 0


def test_frequency_is_shown_but_not_used_to_filter() -> None:
    """A once-cited method reference must reach the model alongside the rest."""

    generator = FakeGenerator({"edges": []})
    type_citations(
        generator,
        title="T",
        works=[
            work("bib1", mentions=1, contexts=("We adopt the estimator here.",)),
            work("bib2", mentions=9, contexts=("Prior work exists [2].",)),
        ],
    )

    prompt = generator.prompts[0]
    assert "cited 1x" in prompt
    assert "cited 9x" in prompt


def test_cue_bearing_sentences_are_preferred_for_display() -> None:
    entry = work(
        contexts=(
            "This area has seen much activity [1].",
            "We use the method of Smith et al. [1] throughout.",
        )
    )

    assert entry.best_contexts(1) == ("We use the method of Smith et al. [1] throughout.",)


def test_rendered_block_carries_sections_and_counts() -> None:
    block = render_references([work(mentions=4, sections=("method", "results"))])

    assert "cited 4x" in block
    assert "method, results" in block


# --- failures ---------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, {}, {"edges": "not a list"}])
def test_a_broken_reply_yields_no_edges(bad: Any) -> None:
    result = type_citations(FakeGenerator(bad), title="T", works=[work()])

    assert result.edges == ()
