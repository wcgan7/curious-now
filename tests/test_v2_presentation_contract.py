"""The contract checks that run before anything reaches a reader.

These are cheap to write and easy to lose: every one of them exists because
the pipeline once shipped the thing it now rejects — a caveat manufactured
from a product detail, a qualification stored beside the prose instead of
inside it, an Explain that restated Glance at greater length.
"""

from __future__ import annotations

from curious_now_v2.core.enums import ClaimKind, ExplanationDepth
from curious_now_v2.generation.client import Completion, Usage
from curious_now_v2.generation.packet import ExtractedClaim, ExtractedPacket
from curious_now_v2.generation.present import (
    Presentation,
    validate,
    validate_title,
)

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
    problems = validate_title("A breakthrough in predicting protein structure")
    assert any("hype" in problem for problem in problems)
    assert validate_title("A model predicts protein structure from sequence") == ()


def test_a_bad_title_does_not_withhold_a_good_explanation() -> None:
    """The contract is explicit: a failed title MUST NOT block publication.

    Title violations used to be folded into the same tuple as layer violations,
    and `_store` multiplied every layer by `presentation.valid` — so one word
    over the limit withdrew a sound Glance and Explain and dropped the story to
    evidence only. The remedy for a bad title is the source's own headline.
    """

    presentation = make_presentation(
        display_title="A breakthrough in predicting protein structure",
    )
    presentation = Presentation(
        **{
            **presentation.__dict__,
            "title_violations": validate_title(presentation.display_title),
            "violations": validate(presentation, make_packet()),
        }
    )
    assert not presentation.title_valid
    assert presentation.valid
    assert presentation.valid_depths == (ExplanationDepth.GLANCE, ExplanationDepth.EXPLAIN)


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


def test_a_short_attribution_still_counts_as_a_qualification() -> None:
    """For a release the qualification can be two words, and often is.

    "Google says", opening a sentence about Google's own product, attributes
    the claim. A three-word floor — there only so a span cannot match by
    accident — rejected exactly that, twice, on a Glance that had done the
    right thing.
    """

    glance = (
        "Google says its updated audio model keeps a live conversation coherent "
        "while it handles a task, bringing in real-time information without "
        "breaking the flow. Picture a voice agent that can act and still "
        "remember what was said earlier. That could make live voice agents "
        "feel more natural to talk to."
    )
    problems = validate(
        make_presentation(
            glance=glance,
            glance_qualification_span="Google says",
        ),
        make_packet(story_kind="release", limitations=()),
    )
    assert problems == ()


def test_a_span_too_short_to_mean_anything_is_still_rejected() -> None:
    problems = validate(
        make_presentation(glance_qualification_span="the"), make_packet()
    )
    assert any("not in the glance" in problem for problem in problems)


def test_a_thin_packet_from_a_long_document_is_a_collapse_not_a_finding() -> None:
    """The same paper gained and lost a rung between runs on identical text.

    Measured over 44 packets, every one carried at least three method claims
    except two runs on one 15,600-word paper, which returned 3 and 10 claims
    with no method among them — while its other runs on the same text returned
    11, 24 and 29. Extraction variance decided whether the story had an Explain.
    """

    from curious_now_v2.generation.packet import _collapsed

    rich = make_packet(kinds=(ClaimKind.METHOD,) * 10)
    assert not _collapsed(rich, words=15_000)

    no_method = make_packet(kinds=(ClaimKind.RESULT,) * 10)
    assert _collapsed(no_method, words=15_000)

    too_few = make_packet(kinds=(ClaimKind.METHOD, ClaimKind.RESULT))
    assert _collapsed(too_few, words=15_000)

    # A short document honestly carries few claims, and must not be retried.
    assert not _collapsed(too_few, words=300)
    assert not _collapsed(no_method, words=300)


def test_generation_runs_stories_concurrently_without_sharing_a_connection() -> None:
    """A psycopg connection is not for sharing between threads.

    Each worker opens its own, which costs nothing beside the minute or more a
    story spends waiting on a model — and is what makes the speed-up safe
    rather than merely fast.
    """

    import inspect

    from curious_now_v2.db import generation

    source = inspect.getsource(generation.run_generation)
    assert "ThreadPoolExecutor" in source
    assert "psycopg.connect(database_url" in source, (
        "each worker must open its own connection"
    )
    assert "workers" in inspect.signature(generation.run_generation).parameters
