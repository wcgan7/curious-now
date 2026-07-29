from __future__ import annotations

import hashlib

import pytest

from tests.fixtures.loader import (
    captured,
    fixture_bytes,
    fixture_path,
    manifest,
)

FIXTURE_NAMES = sorted(manifest())


def test_every_declared_fixture_was_captured() -> None:
    missing = [name for name in FIXTURE_NAMES if not fixture_path(name).exists()]

    assert missing == [], f"run scripts/v2_capture_fixtures.py for: {missing}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_content_matches_its_recorded_checksum(name: str) -> None:
    """Guard against silent corruption or an accidental re-capture."""

    body = fixture_bytes(name)
    recorded = captured()[name]

    assert hashlib.sha256(body).hexdigest() == recorded["sha256"]
    assert len(body) == recorded["bytes"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_looks_like_the_format_it_claims(name: str) -> None:
    body = fixture_bytes(name)
    kind = manifest()[name]["kind"]

    if kind == "pdf":
        assert body[:5] == b"%PDF-"
    elif kind == "jats_xml":
        head = body[:400].decode("utf-8", errors="replace").casefold()
        assert "<?xml" in head or "<article" in head
    else:
        head = body[:2000].decode("utf-8", errors="replace").casefold()
        assert "<html" in head or "<!doctype html" in head


def test_the_corpus_covers_the_formats_extraction_must_handle() -> None:
    kinds = {spec["kind"] for spec in manifest().values()}

    assert {
        "arxiv_html",
        "jats_xml",
        "pdf",
        "news_html",
        "blog_html",
        "institutional_html",
        "publisher_html",
        "biorxiv_html",
    } <= kinds


def test_fixtures_stay_small_enough_to_version() -> None:
    """PDFs dominate: they compress poorly and are stored image-stripped and
    page-limited already. Markup fixtures are a small fraction of the total."""

    total = sum(fixture_path(name).stat().st_size for name in FIXTURE_NAMES)

    assert total < 6_000_000, f"fixture corpus grew to {total:,} bytes"
