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


# --- publisher-native JATS --------------------------------------------------


def test_plos_jats_leads_because_pmc_deposit_lags() -> None:
    """Europe PMC answers pmcid=None for every PLOS paper in this corpus.

    Deposit trails publication by weeks and a feed of new science reads exactly
    the articles PMC has not indexed yet, so the publisher's own XML has to be
    reachable without waiting for the deposit.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "europepmc" in str(request.url):
            return httpx.Response(
                200,
                json={"resultList": {"result": [{"pmcid": None, "isOpenAccess": "N"}]}},
            )
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3003908",
            doi="10.1371/journal.pbio.3003908",
            is_paper=True,
        )

    assert candidates[0].source == "plos_jats"
    assert "plosbiology" in candidates[0].url
    assert "type=manuscript" in candidates[0].url


def test_plos_journal_comes_from_the_doi_infix() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://example.test/a",
            doi="10.1371/journal.pmed.1005208",
            is_paper=True,
        )

    assert "plosmedicine" in candidates[0].url


def test_elife_is_routed_by_url_because_it_has_no_stored_doi() -> None:
    """Not one eLife item in this corpus carries a DOI; the URL carries the id."""

    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://elifesciences.org/articles/110967", is_paper=True
        )

    assert candidates[0].source == "elife_jats"
    assert candidates[0].url.endswith("/110967.xml")


def test_an_unknown_publisher_gets_no_native_candidate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher, url="https://example.test/a", doi="10.9999/unknown.1", is_paper=True
        )

    assert not any(candidate.parser == "jats" for candidate in candidates)


# --- references may come from a candidate that lost on prose ----------------


def _jats_with_refs(words: int = 700) -> str:
    """A commentary: long enough to be real text, no sections to score on.

    Deliberately unstructured, because the point is a candidate that clears the
    length gate and still loses the comparison — which is what the eLife and
    PLOS Medicine commentaries did.
    """

    body = " ".join(f"word{index}" for index in range(words))
    return f"""<?xml version="1.0"?>
<article><front><article-meta><title-group>
<article-title>A short comment</article-title></title-group></article-meta></front>
<body><p>{body} citing <xref ref-type="bibr" rid="r1">1</xref> in passing.</p></body>
<back><ref-list>
<ref id="r1"><element-citation><article-title>Prior finding</article-title>
<pub-id pub-id-type="doi">10.1234/prior</pub-id></element-citation></ref>
<ref id="r2"><element-citation><article-title>Another work</article-title>
<pub-id pub-id-type="doi">10.1234/another</pub-id></element-citation></ref>
</ref-list></back></article>"""


def _long_article_html(words: int = 2400) -> str:
    body = " ".join(f"word{index}" for index in range(words))
    return (
        "<html><head><title>A short comment</title></head><body><article>"
        f"<h1>A short comment</h1><p>{body}</p></article></body></html>"
    )


def test_references_are_kept_from_a_candidate_that_lost_on_prose() -> None:
    """A short piece scores higher as HTML while only its JATS has the list.

    Measured on real items: eLife and PLOS Medicine commentaries lost 10, 10
    and 14 fully identified references this way, for a prose difference of
    around a hundred words.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "journals.plos.org" in request.url.host and "article/file" in str(request.url):
            return httpx.Response(
                200, content=_jats_with_refs().encode(), headers={"content-type": "application/xml"}
            )
        if "europepmc" in str(request.url) or "openalex" in request.url.host:
            return httpx.Response(404)
        return httpx.Response(
            200, content=_long_article_html().encode(), headers={"content-type": "text/html"}
        )

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(
            fetcher,
            url="https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1005208",
            doi="10.1371/journal.pmed.1005208",
            is_paper=True,
        )

    assert resolution.status is ResolutionStatus.OK
    # The bibliography survives whichever candidate won the prose.
    assert len(resolution.references) == 2
    assert resolution.reference_source == "plos_jats"
    assert {reference.doi for reference in resolution.references} == {
        "10.1234/prior",
        "10.1234/another",
    }


def test_reference_source_is_absent_when_nothing_had_a_bibliography() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        maybe = robots(request)
        if maybe is not None:
            return maybe
        if "europepmc" in str(request.url) or "openalex" in request.url.host:
            return httpx.Response(404)
        return httpx.Response(
            200, content=_long_article_html().encode(), headers={"content-type": "text/html"}
        )

    with build_fetcher(handler) as fetcher:
        resolution = resolve_item_text(
            fetcher, url="https://example.test/story", is_paper=False
        )

    assert resolution.status is ResolutionStatus.OK
    assert resolution.references == ()
    assert resolution.reference_source is None


def test_medrxiv_is_routed_to_its_pdf() -> None:
    """Its landing page carries only the abstract, and ".full" returns the same.

    Every medRxiv item in this corpus sat at four to six hundred words for that
    reason, with a DOI prefix too recent for OpenAlex or PMC to offer a route.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://www.medrxiv.org/content/10.64898/2026.07.29.26359192v1?rss=1",
            is_paper=True,
        )

    assert candidates[0].source == "medrxiv_pdf"
    assert candidates[0].parser == "pdf"
    # The feed appends a query string; it must not survive into the path.
    assert candidates[0].url == (
        "https://www.medrxiv.org/content/10.64898/2026.07.29.26359192v1.full.pdf"
    )


def test_biorxiv_uses_the_same_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://www.biorxiv.org/content/10.1101/2026.01.01.123456v2",
            is_paper=True,
        )

    assert candidates[0].source == "biorxiv_pdf"
    assert candidates[0].url.endswith("v2.full.pdf")


def test_a_preprint_url_already_ending_in_full_is_not_doubled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://www.medrxiv.org/content/10.1101/2026.01.01.1v1.full",
            is_paper=True,
        )

    assert candidates[0].url.endswith("v1.full.pdf")
    assert ".full.full" not in candidates[0].url


def test_marked_up_copies_are_tried_before_pdfs() -> None:
    """A publisher serving both must not have its JATS skipped for a PDF."""

    def handler(request: httpx.Request) -> httpx.Response:
        return robots(request) or httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        candidates = discover_candidates(
            fetcher,
            url="https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1",
            doi="10.1371/journal.pbio.1",
            arxiv_id="2607.00001",
            is_paper=True,
        )

    sources = [candidate.source for candidate in candidates]
    assert sources.index("plos_jats") < sources.index("arxiv_pdf")
