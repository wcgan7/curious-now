"""The walkthrough that cites, and the checks on what it cites.

Technical is the only layer a reader opens in order to check something, so an
invented citation is its worst failure — worse than a thin walkthrough, because
it looks like evidence. Retrieval already recovered the document's section,
figure and table labels, so a claimed label can be tested against the labels the
document actually has.
"""

from __future__ import annotations

from typing import Any

from curious_now_v2.generation.client import Completion, Usage
from curious_now_v2.generation.technical import (
    Citation,
    Technical,
    TechnicalSection,
    known_labels,
    validate,
)

STRUCTURE: dict[str, Any] = {
    "sections": [
        {"title": "Methods", "kind": "methods"},
        {"title": "Results", "kind": "results"},
    ],
    "figures": [{"label": "Figure 1"}, {"label": "Figure 4"}],
    "tables": [{"label": "Table 2"}],
}

BODY = " ".join(["The measured response rose with dose in every replicate."] * 40)


def make_technical(**overrides: Any) -> Technical:
    fields: dict[str, Any] = {
        "sections": (
            TechnicalSection("Orientation", BODY),
            TechnicalSection("Approach", BODY),
            TechnicalSection("Results", BODY),
            TechnicalSection("Limitations", BODY),
        ),
        "citations": (
            Citation("Figure 4", "the dose-response curve"),
            Citation("Methods", "how exposure was measured"),
        ),
        "prerequisites": ("dose-response",),
        "eligible": True,
        "declined_reason": "",
        "completion": Completion({}, usage=Usage()),
    }
    fields.update(overrides)
    return Technical(**fields)


def test_accepts_a_walkthrough_that_cites_what_the_document_has() -> None:
    assert validate(make_technical(), STRUCTURE) == ()


def test_rejects_a_citation_the_document_does_not_have() -> None:
    """The one failure that matters most: it looks exactly like evidence."""

    problems = validate(
        make_technical(
            citations=(
                Citation("Figure 9", "a curve that does not exist"),
                Citation("Figure 4", "the real one"),
            )
        ),
        STRUCTURE,
    )
    assert any("does not have" in problem for problem in problems)
    assert any("Figure 9" in problem for problem in problems)


def test_a_label_is_matched_past_punctuation_and_case() -> None:
    """Citing "figure 4:" for a float labelled "Figure 4" is a correct citation.

    The check exists to catch a citation of something absent, not to insist on
    a transcription of the label's trailing colon.
    """

    assert validate(make_technical(citations=(Citation("figure 4:", "x"),)), STRUCTURE) == ()


def test_a_walkthrough_may_use_the_headings_the_work_calls_for() -> None:
    """A proof has a proof strategy; a device has a fabrication process.

    The contract's list is a default, not a vocabulary. Enforcing it would cost
    a paper of another shape its entire Technical layer over a label.
    """

    problems = validate(
        make_technical(
            sections=(
                TechnicalSection("Setting and notation", BODY),
                TechnicalSection("Proof strategy", BODY),
                TechnicalSection("Where the bound is tight", BODY),
                TechnicalSection("What remains open", BODY),
            )
        ),
        STRUCTURE,
    )
    assert problems == ()


def test_a_heading_must_still_be_a_heading() -> None:
    """It is the reader's map through several thousand words."""

    problems = validate(
        make_technical(
            sections=(
                TechnicalSection("Orientation", BODY),
                TechnicalSection(
                    "In this section we describe at some length the manner in "
                    "which the authors approached the problem",
                    BODY,
                ),
            )
        ),
        STRUCTURE,
    )
    assert any("not a heading" in problem for problem in problems)


def test_rejects_a_missing_heading() -> None:
    problems = validate(
        make_technical(
            sections=(
                TechnicalSection("Orientation", BODY),
                TechnicalSection("", BODY),
            )
        ),
        STRUCTURE,
    )
    assert any("no heading" in problem for problem in problems)


def test_rejects_the_same_heading_twice() -> None:
    problems = validate(
        make_technical(
            sections=(
                TechnicalSection("Approach", BODY),
                TechnicalSection("approach", BODY),
            )
        ),
        STRUCTURE,
    )
    assert any("appears twice" in problem for problem in problems)


def test_rejects_unrecovered_maths_reaching_the_reader() -> None:
    problems = validate(
        make_technical(
            sections=(
                TechnicalSection("Orientation", BODY),
                TechnicalSection("Approach", f"{BODY} The model minimises [equation]."),
            )
        ),
        STRUCTURE,
    )
    assert any("maths marker" in problem for problem in problems)


def test_a_walkthrough_too_short_to_inspect_anything_is_rejected() -> None:
    """Unlike Explain's floor, this one means something.

    Methods, evidence, results and limitations cannot be inspected in two
    hundred words; a piece that claims to has summarised, not walked through.
    """

    problems = validate(
        make_technical(sections=(TechnicalSection("Orientation", "Too short."),)),
        STRUCTURE,
    )
    assert any("words" in problem for problem in problems)


def test_declining_is_a_complete_answer_with_a_reason() -> None:
    declined = make_technical(
        eligible=False,
        sections=(),
        citations=(),
        declined_reason="The source reports the finding but never describes the method.",
    )
    assert validate(declined, STRUCTURE) == ()
    assert not declined.valid


def test_declining_without_a_reason_is_not() -> None:
    problems = validate(
        make_technical(eligible=False, sections=(), citations=(), declined_reason=""),
        STRUCTURE,
    )
    assert any("without a reason" in problem for problem in problems)


def test_citing_a_document_with_no_recovered_structure_is_refused() -> None:
    """Nothing can be checked, so nothing may be claimed."""

    problems = validate(make_technical(), {"sections": [], "figures": [], "tables": []})
    assert problems, "citations against an empty structure map must not pass"


def test_known_labels_reads_sections_figures_and_tables() -> None:
    assert known_labels(STRUCTURE) == frozenset(
        {"Methods", "Results", "Figure 1", "Figure 4", "Table 2"}
    )
    assert known_labels(None) == frozenset()


def test_a_double_escaped_newline_never_reaches_the_reader() -> None:
    """Mathematics is full of backslashes, and one too many gets escaped.

    A quantum optimisation walkthrough came back with ten literal "\\n"
    sequences where paragraph breaks belonged. Every LaTeX command starting
    with n continues in lower case, so the distinction is decidable.
    """

    from curious_now_v2.generation.client import unescape_newlines

    text = r"bias at most \(\epsilon/3\).\n\nQHTME is not unbiased, so \nabla F"
    cleaned = unescape_newlines(text)
    assert "\n\n" in cleaned, "the paragraph break must be restored"
    assert r"\nabla" in cleaned, "the gradient operator must survive intact"
    assert r"\n\n" not in cleaned


def test_the_writer_is_shown_what_each_figure_actually_contains() -> None:
    """A citation's purpose was being invented from a bare number.

    "Figure 4 — the dose-response curve" is a claim about what Figure 4 shows,
    and the walkthrough was making it having seen only the string "Figure 4",
    in the one layer whose whole point is that a reader can check it.
    """

    from curious_now_v2.generation.technical import _labelled

    shown = _labelled(
        {"label": "Figure 4", "caption": "Dose-response curves, with 95% intervals."}
    )
    assert shown == "Figure 4 — Dose-response curves, with 95% intervals."
    assert _labelled({"label": "Figure 1", "caption": ""}) == "Figure 1"
    assert _labelled({"label": "", "caption": "an orphan caption"}) == ""


def test_a_very_long_caption_cannot_crowd_out_the_document() -> None:
    from curious_now_v2.generation.technical import _labelled

    shown = _labelled({"label": "Figure 2", "caption": "word " * 200})
    assert len(shown) < 330
    assert shown.endswith("...")
