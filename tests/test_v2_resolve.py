from __future__ import annotations

import gzip
from collections.abc import Callable

import httpx
import pytest

from curious_now_v2.retrieval.document import Document, Section, SectionKind
from curious_now_v2.retrieval.fetch import Fetcher
from curious_now_v2.retrieval.resolve import (
    ResolutionStatus,
    TextKind,
    discover_candidates,
    resolve_item_text,
)
from curious_now_v2.retrieval.select import (
    GOOD_ENOUGH,
    is_good_enough,
    pick_best,
    score_document,
)
from tests.fixtures.loader import fixture_path, fixture_text

Handler = Callable[[httpx.Request], httpx.Response]


def build_fetcher(handler: Handler) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return Fetcher(client=client, sleep=False)


def robots(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    return None


def raw_pdf_bytes() -> bytes:
    return gzip.decompress(fixture_path("arxiv_paper_pdf").read_bytes())


# --- scoring ----------------------------------------------------------------


def make_document(**kwargs: object) -> Document:
    defaults: dict[str, object] = {"extraction_method": "test"}
    defaults.update(kwargs)
    return Document(**defaults)  # type: ignore[arg-type]


def test_a_richer_extraction_outscores_a_thinner_one() -> None:
    thin = make_document(
        sections=(Section(title=None, kind=SectionKind.OTHER, paragraphs=("a " * 300,)),)
    )
    rich = make_document(
        sections=(
            Section(title="Methods", kind=SectionKind.METHOD, paragraphs=("a " * 2000,)),
            Section(title="Results", kind=SectionKind.RESULTS, paragraphs=("b " * 2000,)),
            Section(
                title="Limitations",
                kind=SectionKind.LIMITATIONS,
                paragraphs=("c " * 500,),
            ),
        )
    )

    assert score_document(rich).score > score_document(thin).score


def test_structured_sources_win_a_tie() -> None:
    document = make_document(
        sections=(
            Section(title="Methods", kind=SectionKind.METHOD, paragraphs=("a " * 900,)),
        )
    )

    markup = score_document(document, source="arxiv_html")
    pdf = score_document(document, source="arxiv_pdf")

    assert markup.score > pdf.score


def test_a_warned_extraction_is_penalised() -> None:
    body = (Section(title="Methods", kind=SectionKind.METHOD, paragraphs=("a " * 900,)),)
    clean = score_document(make_document(sections=body))
    warned = score_document(make_document(sections=body, warnings=("truncated",)))

    assert warned.score < clean.score / 1.5


def test_pick_best_ignores_empty_extractions() -> None:
    empty = score_document(make_document(), source="oa_pdf")
    real = score_document(
        make_document(
            sections=(
                Section(title="M", kind=SectionKind.METHOD, paragraphs=("a " * 800,)),
            )
        ),
        source="arxiv_html",
    )

    assert pick_best((empty, real)) is real
    assert pick_best((empty,)) is None


def test_a_full_paper_is_good_enough_to_stop_fetching() -> None:
    """A well extracted paper should short-circuit the walk, so its PDF is
    never pulled — politeness as much as speed."""

    from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html

    document = extract_arxiv_html(fixture_text("arxiv_latexml_html"))

    assert is_good_enough(score_document(document, source="arxiv_html"))


def test_a_thin_page_is_not_good_enough_to_stop() -> None:
    document = make_document(
        sections=(Section(title=None, kind=SectionKind.OTHER, paragraphs=("a " * 200,)),)
    )

    assert score_document(document).score < GOOD_ENOUGH


# --- candidate discovery ----------------------------------------------------


def test_arxiv_html_is_tried_before_its_pdf() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://example.test/a", arxiv_id="2607.07395", is_paper=True
        )

    sources = [candidate.source for candidate in candidates]
    assert sources.index("arxiv_html") < sources.index("arxiv_pdf")


def test_pmc_jats_leads_when_the_doi_is_open_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "europepmc" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "resultList": {
                        "result": [{"pmcid": "PMC123", "isOpenAccess": "Y"}]
                    }
                },
            )
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://example.test/a",
            doi="10.1234/abc",
            is_paper=True,
        )

    assert candidates[0].source == "pmc_jats"
    assert "PMC123" in candidates[0].url


def test_open_access_copies_come_from_openalex() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "openalex" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "best_oa_location": {
                        "is_oa": True,
                        "pdf_url": "https://oa.test/paper.pdf",
                        "landing_page_url": "https://oa.test/paper",
                        "license": "cc-by",
                    },
                    "locations": [],
                },
            )
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://example.test/a", doi="10.1234/abc", is_paper=True
        )

    by_source = {candidate.source: candidate for candidate in candidates}
    assert by_source["oa_pdf"].url == "https://oa.test/paper.pdf"
    assert by_source["oa_pdf"].licence == "cc-by"


def test_a_news_item_has_only_its_own_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(fetcher, url="https://news.test/story")

    assert [candidate.source for candidate in candidates] == ["article_html"]


def test_candidates_are_deduplicated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "openalex" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://example.test/a",
                    },
                    "locations": [],
                },
            )
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://example.test/a", doi="10.1/x", is_paper=True
        )

    urls = [candidate.url for candidate in candidates]
    assert len(urls) == len(set(urls))


# --- end to end -------------------------------------------------------------


def test_arxiv_html_wins_and_the_pdf_is_never_fetched() -> None:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        fetched.append(str(request.url))
        if "/html/" in request.url.path:
            return httpx.Response(
                200,
                content=fixture_text("arxiv_latexml_html").encode(),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(200, content=raw_pdf_bytes())

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(
            fetcher,
            url="https://arxiv.org/abs/2607.07395",
            arxiv_id="2607.07395",
            is_paper=True,
        )

    assert resolution.status is ResolutionStatus.OK
    assert resolution.source == "arxiv_html"
    assert resolution.kind is TextKind.FULL_TEXT
    assert not any("/pdf/" in url for url in fetched)


def test_the_pdf_is_used_when_no_html_rendering_exists() -> None:
    """arXiv has no LaTeXML for every paper, which is what the PDF path is for."""

    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "/html/" in request.url.path:
            return httpx.Response(404)
        if "/pdf/" in request.url.path:
            return httpx.Response(
                200,
                content=raw_pdf_bytes(),
                headers={"content-type": "application/pdf"},
            )
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(
            fetcher, url="https://arxiv.org/abs/x", arxiv_id="2607.24758", is_paper=True
        )

    assert resolution.status is ResolutionStatus.OK
    assert resolution.source == "arxiv_pdf"
    assert resolution.document is not None
    assert resolution.document.has_method_section


def test_a_paywalled_page_is_reported_as_paywalled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        return httpx.Response(
            200,
            content=fixture_text("statnews_html").encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(fetcher, url="https://www.statnews.com/a")

    assert resolution.status is ResolutionStatus.PAYWALLED
    assert resolution.document is None


def test_a_robots_block_is_distinguished_from_an_absent_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, content=b"should never be fetched")

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(fetcher, url="https://blocked.test/story")

    assert resolution.status is ResolutionStatus.BLOCKED


def test_an_item_with_no_url_or_identifier_resolves_to_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(fetcher, url="")

    assert resolution.status is ResolutionStatus.NOT_FOUND


def test_a_short_page_resolves_as_abstract_rather_than_full_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        return httpx.Response(
            200,
            content=fixture_text("bbc_news_html").encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(fetcher, url="https://www.bbc.co.uk/news/x")

    assert resolution.status is ResolutionStatus.OK
    assert resolution.kind is TextKind.ABSTRACT


def test_every_attempt_is_recorded_for_the_operator() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "/html/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(
            200, content=raw_pdf_bytes(), headers={"content-type": "application/pdf"}
        )

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(
            fetcher, url="https://arxiv.org/abs/x", arxiv_id="2607.24758", is_paper=True
        )

    assert "arxiv_html" in resolution.attempted
    assert "arxiv_pdf" in resolution.attempted
    assert any("not_found" in reason for reason in resolution.reasons)


@pytest.mark.parametrize(
    "payload", ["not json at all", '{"resultList": {}}', "{}"]
)
def test_malformed_provider_responses_do_not_break_discovery(payload: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "europepmc" in str(request.url) or "openalex" in request.url.host:
            return httpx.Response(200, content=payload.encode())
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://example.test/a", doi="10.1/x", is_paper=True
        )

    assert [candidate.source for candidate in candidates] == ["article_html"]
