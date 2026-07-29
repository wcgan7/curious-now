from __future__ import annotations

from curious_now_v2.core.enums import AccessClass
from curious_now_v2.pipeline.hydrate import (
    ARXIV_BATCH_SIZE,
    arxiv_batches,
    clean_abstract,
    parse_arxiv_response,
    parse_crossref_work,
)

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.01234v2</id>
    <title>A measured result</title>
    <summary>
      We introduce a method that preserves information across layers and
      evaluate it against strong baselines on several public benchmarks.
    </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.05678</id>
    <title>Another result</title>
    <summary>Too short</summary>
  </entry>
</feed>
"""


def test_versioned_arxiv_ids_map_back_to_the_bare_identifier() -> None:
    parsed = parse_arxiv_response(ARXIV_FEED)

    assert "2601.01234" in parsed
    assert parsed["2601.01234"].access_class is AccessClass.ABSTRACT
    assert parsed["2601.01234"].extraction_method == "arxiv_api"


def test_entries_without_a_usable_abstract_are_skipped() -> None:
    parsed = parse_arxiv_response(ARXIV_FEED)

    assert "2601.05678" not in parsed


def test_malformed_arxiv_payload_returns_no_hydrations() -> None:
    assert parse_arxiv_response("<feed><entry>") == {}


def test_crossref_jats_markup_is_stripped() -> None:
    hydration = parse_crossref_work(
        {
            "message": {
                "abstract": (
                    "<jats:p>We report a controlled trial measuring the "
                    "effect across two independent cohorts and find a "
                    "modest improvement.</jats:p>"
                )
            }
        }
    )

    assert hydration is not None
    assert "<jats:p>" not in hydration.abstract
    assert hydration.abstract.startswith("We report a controlled trial")
    assert hydration.extraction_method == "crossref_api"


def test_crossref_work_without_an_abstract_is_skipped() -> None:
    assert parse_crossref_work({"message": {"title": ["No abstract here"]}}) is None
    assert parse_crossref_work({}) is None


def test_jats_section_heading_is_not_kept_as_body_text() -> None:
    hydration = parse_crossref_work(
        {
            "message": {
                "abstract": (
                    "<jats:title>Abstract</jats:title><jats:p>Large genome "
                    "databases have markedly improved our understanding of "
                    "marine microorganisms across many ocean basins.</jats:p>"
                )
            }
        }
    )

    assert hydration is not None
    assert hydration.abstract.startswith("Large genome databases")


def test_placeholder_abstracts_are_rejected() -> None:
    assert clean_abstract("Abstract") is None
    assert clean_abstract("No abstract available") is None
    assert clean_abstract("   ") is None
    assert clean_abstract(None) is None


def test_entities_are_unescaped_and_whitespace_collapsed() -> None:
    cleaned = clean_abstract(
        "We  studied\n\nR&amp;D   spending across   many   institutions "
        "and report a measurable difference between the two groups."
    )

    assert cleaned is not None
    assert "R&D spending" in cleaned
    assert "  " not in cleaned


def test_batches_respect_the_api_limit_and_drop_duplicates() -> None:
    ids = tuple(f"2601.{index:05d}" for index in range(120)) + ("2601.00000",)

    batches = arxiv_batches(ids)

    assert all(len(batch) <= ARXIV_BATCH_SIZE for batch in batches)
    flattened = [value for batch in batches for value in batch]
    assert len(flattened) == len(set(flattened)) == 120


def test_empty_identifier_list_produces_no_batches() -> None:
    assert arxiv_batches(()) == ()
    assert arxiv_batches(("", "   ")) == ()
