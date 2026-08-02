from __future__ import annotations

import os
from uuid import UUID

import psycopg
import pytest

from curious_now_v2.db.citations import (
    guess_title,
    store_typed_edges,
)
from curious_now_v2.generation.citations import CitedWork, TypedEdge

DATABASE_URL = os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="CURIOUS_NOW_V2_DATABASE_URL is not set"
)


@pytest.fixture
def conn():
    with psycopg.connect(DATABASE_URL) as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def citing_item(conn) -> tuple[UUID, UUID]:
    """An item with a paper of its own, which an edge can start from."""

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE active LIMIT 1;")
        source_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO items (source_id, source_native_id, url, canonical_url,
                                  canonical_hash, title, content_type)
               VALUES (%s, %s, %s, %s, %s, %s, 'preprint') RETURNING id;""",
            (
                source_id, "edge-test-native", "https://example.test/edge-test",
                "https://example.test/edge-test", "edgetesthash1", "Citing paper",
            ),
        )
        item_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO papers (title, doi, access_class)
               VALUES ('Citing paper', %s, 'open_full_text') RETURNING id;""",
            (f"10.9999/citing.{item_id}",),
        )
        paper_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO item_papers (item_id, paper_id, match_kind)
               VALUES (%s, %s, 'doi');""",
            (item_id, paper_id),
        )
    return item_id, paper_id


def work(key="bib1", *, doi=None, arxiv_id=None, text="Smith, J. A fine study of things. Journal 1, 1 (2020).") -> CitedWork:
    return CitedWork(
        ref_key=key,
        label="1",
        citation_text=text,
        doi=doi,
        arxiv_id=arxiv_id,
        mentions=2,
        cited_sections=("method",),
        contexts=("We adopt the estimator of Smith et al. [1].",),
    )


def edge(key="bib1", relation="applies") -> TypedEdge:
    return TypedEdge(key, relation, "We adopt the estimator of Smith et al.", "uses it")


# --- writing edges ----------------------------------------------------------


def test_an_edge_creates_a_stub_for_its_target(conn, citing_item) -> None:
    item_id, citing_paper = citing_item
    reference = work(doi="10.9999/target.one")

    result = store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[reference],
        prompt_version="test-v1",
    )

    assert result.written == 1
    assert result.stubs_created == 1
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.title, p.access_class, p.metadata->>'origin'
               FROM paper_relations r JOIN papers p ON p.id = r.to_paper_id
               WHERE r.from_paper_id = %s;""",
            (citing_paper,),
        )
        title, access, origin = cur.fetchone()
    assert access == "metadata_only"
    assert origin == "citation_stub"
    assert "fine study" in title


def test_the_quote_is_stored_as_the_edge_s_warrant(conn, citing_item) -> None:
    """The claim is only as good as the sentence it points at."""

    item_id, citing_paper = citing_item
    store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[work(doi="10.9999/target.two")],
        prompt_version="test-v1",
    )

    with conn.cursor() as cur:
        cur.execute(
            """SELECT relation, source, provenance->>'quote', provenance->>'mentions'
               FROM paper_relations WHERE from_paper_id = %s;""",
            (citing_paper,),
        )
        relation, source, quote, mentions = cur.fetchone()

    assert relation == "applies"
    assert source == "paper_text"
    assert quote.startswith("We adopt the estimator")
    assert mentions == "2"


def test_an_existing_paper_is_reused_not_duplicated(conn, citing_item) -> None:
    item_id, _ = citing_item
    doi = "10.9999/already.here"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO papers (title, doi, access_class) VALUES ('Real paper', %s, 'abstract');",
            (doi,),
        )

    result = store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[work(doi=doi)],
        prompt_version="test-v1",
    )

    assert result.stubs_created == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(title) FROM papers WHERE lower(doi) = lower(%s);", (doi,))
        count, title = cur.fetchone()
    assert count == 1
    assert title == "Real paper"


def test_a_reference_without_an_identifier_is_skipped(conn, citing_item) -> None:
    """A citation string alone cannot be deduplicated across a corpus."""

    item_id, _ = citing_item
    result = store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[work()],
        prompt_version="test-v1",
    )

    assert result.written == 0
    assert any("no identifier" in reason for reason in result.skipped)


def test_a_self_citation_is_refused(conn, citing_item) -> None:
    """paper_relations forbids it, and it is not an edge worth traversing."""

    item_id, citing_paper = citing_item
    with conn.cursor() as cur:
        cur.execute("SELECT doi FROM papers WHERE id = %s;", (citing_paper,))
        own_doi = cur.fetchone()[0]

    result = store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[work(doi=own_doi)],
        prompt_version="test-v1",
    )

    assert result.written == 0
    assert any("itself" in reason for reason in result.skipped)


def test_rewriting_an_edge_updates_its_evidence(conn, citing_item) -> None:
    """Re-running the typing pass must refresh, not duplicate."""

    item_id, citing_paper = citing_item
    reference = work(doi="10.9999/target.three")
    store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[reference],
        prompt_version="test-v1",
    )
    store_typed_edges(
        conn, item_id=item_id,
        edges=(TypedEdge("bib1", "applies", "A different quote entirely.", "why"),),
        works=[reference], prompt_version="test-v2",
    )

    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*), max(provenance->>'prompt_version')
               FROM paper_relations WHERE from_paper_id = %s;""",
            (citing_paper,),
        )
        count, version = cur.fetchone()
    assert count == 1
    assert version == "test-v2"


def test_an_item_with_no_paper_writes_nothing(conn) -> None:
    """Journalism has no paper of its own, so it can start no paper->paper edge."""

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE active LIMIT 1;")
        source_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO items (source_id, source_native_id, url, canonical_url,
                                  canonical_hash, title, content_type)
               VALUES (%s, 'no-paper', 'https://example.test/news',
                       'https://example.test/news', 'nopaperhash1', 'A story', 'news')
               RETURNING id;""",
            (source_id,),
        )
        item_id = cur.fetchone()[0]

    result = store_typed_edges(
        conn, item_id=item_id, edges=(edge(),), works=[work(doi="10.9999/x")],
        prompt_version="test-v1",
    )

    assert result.written == 0
    assert result.skipped == ("citing item has no paper record",)


# --- stub titles ------------------------------------------------------------


@pytest.mark.parametrize(
    ("citation", "expected"),
    [
        (
            "Vaswani, A. et al. Attention is all you need. NeurIPS (2017).",
            "Attention is all you need",
        ),
        (
            "Smith, J.; Jones, K. A study of signed networks. In Proceedings of ICDM, 2016.",
            "A study of signed networks",
        ),
    ],
)
def test_a_title_is_recovered_from_the_citation(citation: str, expected: str) -> None:
    assert guess_title(citation) == expected


def test_a_citation_with_no_recoverable_title_still_yields_one() -> None:
    """papers.title is NOT NULL, so this must never return empty."""

    assert guess_title("???").strip()
    assert guess_title("").strip()


# --- run accounting ---------------------------------------------------------


def test_skip_reasons_are_counted_not_discarded(conn, citing_item, monkeypatch) -> None:
    """Without this the cost of unresolved identifiers cannot be known.

    The first full run threw these away, leaving "is it worth paying an index
    to resolve the rest" answerable only by guessing.
    """

    from curious_now_v2.db import citations as module

    item_id, _ = citing_item
    works = [work("bib1"), work("bib2", doi="10.9999/has.id")]

    result = module.store_typed_edges(
        conn,
        item_id=item_id,
        edges=(edge("bib1"), edge("bib2")),
        works=works,
        prompt_version="test-v1",
    )

    assert result.written == 1
    assert any("no identifier" in reason for reason in result.skipped)


def test_blocked_by_identifier_counts_only_that_reason() -> None:
    from collections import Counter

    from curious_now_v2.db.citations import TypingRunResult

    run = TypingRunResult(
        skipped=Counter(
            {
                "no identifier to key a paper on": 7,
                "cites itself": 2,
                "no such reference": 1,
            }
        )
    )

    assert run.blocked_by_identifier == 7
