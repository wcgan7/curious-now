from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from curious_now_v2.retrieval.reference_lookup import (
    MIN_TITLE_OVERLAP,
    LookupUnavailable,
    clean_citation,
    resolve,
    title_overlap,
)

KUMAR = (
    "Kumar, S., Spezzano, F., Subrahmanian, V.S., Faloutsos, C. "
    "Edge weight prediction in weighted signed networks. "
    "In 2016 IEEE 16th International Conference on Data Mining (ICDM)."
)


def reply(item: dict[str, Any] | None):
    """An opener returning one Crossref item, or none."""

    payload = json.dumps({"message": {"items": [item] if item else []}}).encode()

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def opener(request: Any, timeout: float = 0) -> Any:
        return _Response(payload)

    return opener


def item(
    title: str = "Edge weight prediction in weighted signed networks",
    *,
    doi: str | None = "10.1109/icdm.2016.0033",
    family: str = "Kumar",
) -> dict[str, Any]:
    return {
        "title": [title],
        "DOI": doi,
        "author": [{"family": family}],
        "score": 130.0,
    }


# --- the guard --------------------------------------------------------------


def test_a_good_match_is_accepted() -> None:
    match = resolve(KUMAR, opener=reply(item()))

    assert match is not None
    assert match.doi == "10.1109/icdm.2016.0033"
    assert match.confidence > MIN_TITLE_OVERLAP


def test_a_wrong_title_is_refused() -> None:
    """A confident wrong match invents a paper and an edge pointing at it.

    Crossref returned exactly this shape on real data: "A Disentangled
    Recognition and Nonlinear Dynamics Model" matched "Disentangled
    Unsupervised Skill Discovery" at 0.38 overlap.
    """

    wrong = item(title="Disentangled unsupervised skill discovery", family="Park")

    assert resolve(KUMAR, opener=reply(wrong)) is None


def test_a_partial_title_without_the_author_is_refused() -> None:
    partial = item(
        title="Edge weight prediction in weighted signed networks using autoencoders",
        family="Nobody",
    )

    assert resolve(KUMAR, opener=reply(partial)) is None


def test_the_same_partial_title_passes_when_an_author_agrees() -> None:
    near = item(
        title="Edge weight prediction in weighted signed networks today",
        family="Kumar",
    )

    match = resolve(KUMAR, opener=reply(near))

    assert match is not None
    assert match.confidence < 1.0


def test_a_match_with_no_doi_is_refused() -> None:
    assert resolve(KUMAR, opener=reply(item(doi=None))) is None


def test_no_results_yields_nothing() -> None:
    assert resolve(KUMAR, opener=reply(None)) is None


def test_a_citation_too_short_to_match_never_asks() -> None:
    calls: list[Any] = []

    def opener(request: Any, timeout: float = 0) -> Any:
        calls.append(request)
        raise AssertionError("should not have been called")

    assert resolve("Ibid., p. 4.", opener=opener) is None
    assert calls == []


def test_only_the_leading_authors_corroborate_a_partial_title() -> None:
    """A citation abbreviates to "et al.", so it lists the first authors only.

    A tenth author appearing in Crossref but not in the citation is therefore no
    evidence either way, and must not be allowed to rescue a partial title
    match that nothing else supports.
    """

    partial = item(title="Edge weight prediction in weighted signed networks today")
    partial["author"] = [
        {"family": f"Author{index}"} for index in range(9)
    ] + [{"family": "Kumar"}]

    assert resolve(KUMAR, opener=reply(partial)) is None


# --- availability versus absence --------------------------------------------


def test_being_unable_to_ask_is_distinct_from_finding_nothing() -> None:
    """Reporting a refusal as a miss makes a blocked run look like a bad corpus.

    A rate limit did exactly that: 32 references were recorded as unmatchable
    when the index had simply stopped answering.
    """

    def opener(request: Any, timeout: float = 0) -> Any:
        raise OSError("connection reset")

    with pytest.raises(LookupUnavailable):
        resolve(KUMAR, opener=opener)


def test_a_transient_rate_limit_is_waited_out_and_retried() -> None:
    """One 429 in a run of eight thousand is impatience, not a reason to stop."""

    attempts: list[int] = []

    def opener(request: Any, timeout: float = 0) -> Any:
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                "https://api.crossref.org/works", 429, "Too Many Requests", {},
                io.BytesIO(b"{}"),
            )
        return reply(item())(request, timeout)

    match = resolve(KUMAR, opener=opener, sleeper=lambda _seconds: None)

    assert match is not None
    assert len(attempts) == 2


def test_a_sustained_rate_limit_is_reported_as_unavailable() -> None:
    def opener(request: Any, timeout: float = 0) -> Any:
        raise urllib.error.HTTPError(
            "https://api.crossref.org/works", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error":"Rate limit exceeded"}'),
        )

    with pytest.raises(LookupUnavailable, match="429"):
        resolve(KUMAR, opener=opener, sleeper=lambda _seconds: None)


# --- cleaning ---------------------------------------------------------------


def test_latexml_back_references_are_stripped() -> None:
    """They are our reader's annotations, not part of the citation."""

    polluted = (
        "A. Cornelissen, Y. Hamoudi (2022) Near-optimal quantum algorithms. "
        "Cited by: §A.1 , §A.1 , Appendix B , Lemma C.23 , 1st item ,"
    )

    cleaned = clean_citation(polluted)

    assert "Cited by" not in cleaned
    assert cleaned.endswith("Near-optimal quantum algorithms.")


def test_external_link_furniture_is_stripped() -> None:
    cleaned = clean_citation(
        "Alignment pretraining: AI discourse. External Links: 2601.12345, Link"
    )

    assert "External Links" not in cleaned


def test_cleaning_leaves_an_ordinary_citation_alone() -> None:
    assert clean_citation(KUMAR) == " ".join(KUMAR.split())


# --- overlap ----------------------------------------------------------------


def test_overlap_is_measured_against_the_citation() -> None:
    assert title_overlap("Edge weight prediction in weighted signed networks", KUMAR) == 1.0


def test_stopwords_do_not_inflate_agreement() -> None:
    assert title_overlap("A study of the in and for", KUMAR) == 0.0


@pytest.mark.parametrize("title", ["", "   ", "the of and"])
def test_a_title_with_no_content_scores_zero(title: str) -> None:
    assert title_overlap(title, KUMAR) == 0.0


def test_an_arxiv_doi_yields_the_arxiv_id() -> None:
    match = resolve(
        "Vaswani, A. Attention is all you need. NeurIPS, 2017, pages 5998-6008.",
        opener=reply(
            item(
                title="Attention is all you need",
                doi="10.48550/arXiv.1706.03762",
                family="Vaswani",
            )
        ),
    )

    assert match is not None
    assert match.arxiv_id == "1706.03762"


# --- year ------------------------------------------------------------------


def issued(item_dict: dict[str, Any], year: int) -> dict[str, Any]:
    item_dict["issued"] = {"date-parts": [[year, 1, 1]]}
    return item_dict


def test_a_matching_title_in_the_wrong_year_is_refused() -> None:
    """Seen on real data: a 2016 citation matched a 2019 article of that title."""

    cited_2016 = (
        "Gwinn RE Krajbich I 2016 Attitudes and attention: how attitude "
        "accessibility and certainty influence attention and choice."
    )
    matched = issued(
        item(
            title="Attitudes and attention: how attitude accessibility and "
            "certainty influence attention and choice",
            family="Gwinn",
        ),
        2019,
    )

    assert resolve(cited_2016, opener=reply(matched)) is None


def test_a_preprint_year_within_tolerance_is_kept() -> None:
    """A preprint and its published version are one work, a year or two apart."""

    cited_2016 = (
        "Gwinn RE Krajbich I 2016 Attitudes and attention: how attitude "
        "accessibility and certainty influence attention and choice."
    )
    matched = issued(
        item(
            title="Attitudes and attention: how attitude accessibility and "
            "certainty influence attention and choice",
            family="Gwinn",
        ),
        2017,
    )

    assert resolve(cited_2016, opener=reply(matched)) is not None


def test_a_citation_naming_no_year_is_not_penalised() -> None:
    """Silence is not disagreement; many citations omit the year."""

    assert resolve(KUMAR.replace("2016", ""), opener=reply(issued(item(), 2016))) is not None
