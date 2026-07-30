"""The contract checks that run before anything reaches a reader.

These are cheap to write and easy to lose: every one of them exists because
the pipeline once shipped the thing it now rejects — a caveat manufactured
from a product detail, a qualification stored beside the prose instead of
inside it, an Explain that restated Glance at greater length.
"""

from __future__ import annotations

from curious_now_v2.core.enums import ClaimKind
from curious_now_v2.generation.client import Completion, Usage
from curious_now_v2.generation.packet import ExtractedClaim, ExtractedPacket
from curious_now_v2.generation.present import Presentation, validate

GLANCE = (
    "Researchers trained a model to predict how a protein folds from its "
    "sequence alone. The trick is to treat the sequence as a set of "
    "constraints rather than a recipe: each amino acid narrows the shapes the "
    "chain can take, and the model searches what is left. That matters "
    "because folding determines what a protein does, and measuring it in a "
    "laboratory takes months. The work was tested on soluble proteins only, "
    "so it says nothing yet about the membrane proteins most drugs target."
)
QUALIFICATION = "tested on soluble proteins only"

EXPLAIN = (
    "The model represents each residue as a vector and updates it against "
    "every other residue, so a contact far along the chain can still pull two "
    "regions together. Training rewards agreement with measured structures, "
    "which pushes the representation toward geometries that are physically "
    "reachable rather than merely plausible. Because supervision comes from "
    "the structures we happen to have solved, families that are absent from "
    "that record are also absent from what the model has learned to expect."
)


def make_packet(
    *,
    kinds: tuple[ClaimKind, ...] = (ClaimKind.RESULT, ClaimKind.METHOD),
    limitations: tuple[str, ...] = ("Only soluble proteins were tested.",),
    story_kind: str = "research_result",
) -> ExtractedPacket:
    return ExtractedPacket(
        story_kind=story_kind,
        central_claim="A model predicts protein structure from sequence.",
        claims=tuple(
            ExtractedClaim(kind=kind, text=f"a {kind.value} claim", confidence=0.9,
                           excerpt="a verbatim span")
            for kind in kinds
        ),
        limitations=limitations,
        prerequisites=(),
        completion=Completion({}, usage=Usage()),
    )


def make_presentation(**overrides: object) -> Presentation:
    fields: dict[str, object] = {
        "spine_novelty": "Structure prediction from sequence alone.",
        "spine_intuition": "The sequence constrains the shape.",
        "spine_qualification": "Soluble proteins only.",
        "display_title": "A model predicts protein structure from sequence alone",
        "glance": GLANCE,
        "glance_qualification_span": QUALIFICATION,
        "glance_supported": True,
        "explain": EXPLAIN,
        "explain_supported": True,
        "explain_declined_reason": "",
        "completion": Completion({}, usage=Usage()),
    }
    fields.update(overrides)
    return Presentation(**fields)  # type: ignore[arg-type]


def test_accepts_a_presentation_that_meets_the_contract() -> None:
    assert validate(make_presentation(), make_packet()) == ()


def test_qualification_must_appear_in_the_prose_the_reader_reads() -> None:
    """The span is the proof of integration, not a second place to write it.

    A qualification held in a field beside the text is invisible to any
    surface that renders only the prose — which is what the reader does.
    """

    problems = validate(
        make_presentation(glance_qualification_span="the sample was small"),
        make_packet(),
    )
    assert any("not in the glance" in problem for problem in problems)


def test_rejects_a_qualification_labelled_as_a_caveat() -> None:
    glance = GLANCE + " Caveat: results are preliminary."
    problems = validate(
        make_presentation(
            glance=glance,
            glance_qualification_span="Caveat: results are preliminary.",
        ),
        make_packet(),
    )
    assert any("labelled" in problem for problem in problems)


def test_requires_a_qualification_where_the_evidence_carries_one() -> None:
    problems = validate(
        make_presentation(glance_qualification_span=""), make_packet()
    )
    assert any("omits a qualification" in problem for problem in problems)


def test_allows_no_qualification_where_the_evidence_carries_none() -> None:
    """Demanding one everywhere is what produced "still in beta"."""

    packet = make_packet(
        kinds=(ClaimKind.RESULT, ClaimKind.METHOD), limitations=()
    )
    assert validate(make_presentation(glance_qualification_span=""), packet) == ()


def test_a_release_always_owes_the_reader_attribution() -> None:
    """An interested party describing its own work qualifies it by saying so."""

    packet = make_packet(
        kinds=(ClaimKind.RESULT, ClaimKind.METHOD),
        limitations=(),
        story_kind="release",
    )
    problems = validate(make_presentation(glance_qualification_span=""), packet)
    assert any("omits a qualification" in problem for problem in problems)


def test_rejects_a_qualification_about_the_source_rather_than_the_science() -> None:
    glance = GLANCE + " The paper does not say how many runs were made."
    problems = validate(
        make_presentation(
            glance=glance,
            glance_qualification_span="The paper does not say how many runs",
        ),
        make_packet(),
    )
    assert any("describes the source" in problem for problem in problems)


def test_rejects_hype_in_the_title() -> None:
    problems = validate(
        make_presentation(display_title="A breakthrough in predicting protein structure"),
        make_packet(),
    )
    assert any("hype" in problem for problem in problems)


def test_rejects_an_explain_that_lifts_a_sentence_from_glance() -> None:
    lifted = GLANCE.split(". ")[1] + "."
    problems = validate(
        make_presentation(explain=f"{lifted} {EXPLAIN}"), make_packet()
    )
    assert any("reuses a sentence" in problem for problem in problems)


def test_rejects_an_explain_with_no_mechanism_behind_it() -> None:
    """Explain answers how it works; claims that describe no method cannot."""

    problems = validate(
        make_presentation(), make_packet(kinds=(ClaimKind.RESULT, ClaimKind.LIMITATION))
    )
    assert any("mechanism the packet does not support" in p for p in problems)


def test_rejects_unrecovered_maths_reaching_the_reader() -> None:
    problems = validate(
        make_presentation(explain=EXPLAIN + " The model minimises [equation]."),
        make_packet(),
    )
    assert any("maths marker" in problem for problem in problems)


def test_a_decline_must_carry_a_reason() -> None:
    problems = validate(
        make_presentation(
            explain="", explain_supported=False, explain_declined_reason=""
        ),
        make_packet(),
    )
    assert any("declined without a reason" in problem for problem in problems)


def test_only_developments_are_worth_publishing() -> None:
    """A podcast is an announcement however scientific its subject.

    An explainer is the opposite case and easy to lose: it reports nothing new,
    and is still mechanism throughout, which is what the ladder is for.
    """

    assert make_packet(story_kind="research_result").worth_publishing
    assert make_packet(story_kind="release").worth_publishing
    assert make_packet(story_kind="explainer").worth_publishing
    assert not make_packet(story_kind="announcement").worth_publishing
    assert not make_packet(story_kind="not_science").worth_publishing
