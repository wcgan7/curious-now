from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from curious_now_v2.core.enums import (
    AccessClass,
    ContentType,
    SourceRole,
)
from curious_now_v2.core.source_registry import load_source_registry
from curious_now_v2.pipeline.ingest import (
    RawFeedEntry,
    canonicalize_url,
    extract_scholarly_ids,
    normalize_entry,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://Example.COM:443//paper/?b=2&utm_source=test&a=1#results",
            "https://example.com/paper?a=1&b=2",
        ),
        (
            "example.com/story/",
            "https://example.com/story",
        ),
        (
            "http://user:secret@example.com:80/story?fbclid=abc",
            "http://example.com/story",
        ),
    ],
)
def test_canonicalize_url_is_deterministic(raw: str, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_canonicalize_url_rejects_non_web_schemes() -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        canonicalize_url("file:///tmp/paper.pdf")


def test_extract_scholarly_ids_handles_feed_text_boundaries() -> None:
    arxiv_id, doi = extract_scholarly_ids(
        "arXiv:2607.12345v2 doi:10.1038/example.42The result follows"
    )

    assert arxiv_id == "2607.12345v2"
    assert doi == "10.1038/example.42"


def test_normalize_entry_produces_an_exact_idempotency_key() -> None:
    entry = RawFeedEntry(
        source_id=uuid4(),
        source_name="Example Lab",
        source_role=SourceRole.LAB_ANNOUNCEMENT,
        source_native_id="post-42",
        title="  A   new result  ",
        url="https://example.test/result/?utm_campaign=launch",
        summary=" A short provider summary. ",
        default_content_type=ContentType.LAB_ANNOUNCEMENT,
    )

    candidate = normalize_entry(entry)

    assert candidate.canonical_url == "https://example.test/result"
    assert candidate.canonical_hash == hashlib.sha256(
        candidate.canonical_url.encode()
    ).hexdigest()
    assert candidate.title == "A new result"
    assert candidate.snippet == "A short provider summary."
    assert candidate.access_class is AccessClass.SNIPPET


def test_checked_in_source_registry_is_valid_and_diverse() -> None:
    registry_path = (
        Path(__file__).parents[1] / "config" / "v2" / "sources.json"
    )

    registry = load_source_registry(registry_path)

    roles = {source.role for source in registry.sources}
    assert len(registry.sources) >= 12
    assert SourceRole.PRIMARY_RESEARCH in roles
    assert SourceRole.JOURNALISM in roles
    assert SourceRole.LAB_ANNOUNCEMENT in roles
    assert SourceRole.GOVERNMENT in roles
