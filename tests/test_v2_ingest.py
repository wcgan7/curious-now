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
from curious_now_v2.core.source_registry import (
    ContentTypeRule,
    load_source_registry,
)
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


def test_entry_category_can_type_an_item_from_a_mixed_journal_feed() -> None:
    entry = RawFeedEntry(
        source_id=uuid4(),
        source_name="Mixed Journal",
        source_role=SourceRole.PRIMARY_RESEARCH,
        title="A measured bioengineering result",
        url="https://example.test/articles/42",
        default_content_type=ContentType.OTHER,
        content_type_rules=(
            ContentTypeRule(
                pattern="Original Research",
                content_type=ContentType.PEER_REVIEWED,
            ),
        ),
        content_type_hints=("Original Research",),
    )

    candidate = normalize_entry(entry)

    assert candidate.content_type is ContentType.PEER_REVIEWED
    assert candidate.content_type_basis == "source_pattern"


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


def make_nature_entry(url: str, *, rules: bool = True) -> RawFeedEntry:
    """Nature's feed carries research, news, comment and reviews down one URL."""

    return RawFeedEntry(
        source_id=uuid4(),
        source_name="Nature",
        source_role=SourceRole.PRIMARY_RESEARCH,
        title="A title",
        url=url,
        default_content_type=ContentType.PEER_REVIEWED,
        content_type_rules=(
            (
                ContentTypeRule(pattern="d41586-", content_type=ContentType.NEWS),
                ContentTypeRule(
                    pattern="s41586-", content_type=ContentType.PEER_REVIEWED
                ),
            )
            if rules
            else ()
        ),
    )


def test_an_item_is_typed_from_its_own_identifier() -> None:
    """The feed default described the feed, and mislabelled most of what came.

    Nature's RSS supplies no category at all, so the identifier is the only
    signal available: research is 10.1038/s41586-, everything editorial is
    10.1038/d41586-.
    """

    review = normalize_entry(
        make_nature_entry("https://www.nature.com/articles/d41586-026-02311-z")
    )
    assert review.content_type is ContentType.NEWS
    assert review.content_type_basis == "source_pattern"

    paper = normalize_entry(
        make_nature_entry("https://www.nature.com/articles/s41586-026-10923-8")
    )
    assert paper.content_type is ContentType.PEER_REVIEWED
    assert paper.content_type_basis == "source_pattern"


def test_a_default_from_a_single_kind_feed_still_describes_the_item() -> None:
    """Not every default is a guess, and treating them alike loses the truth.

    arXiv's feed carries preprints and nothing else, so "preprint" is a fact
    about every item on it. An earlier version of this check withheld the
    Preprint badge from 526 items to protect against a fault none of them had.
    """

    candidate = normalize_entry(
        make_nature_entry("https://www.nature.com/articles/whatever", rules=False)
    )
    assert candidate.content_type is ContentType.PEER_REVIEWED
    assert candidate.content_type_basis == "feed_default"


def test_a_default_reached_on_a_mixed_feed_establishes_nothing() -> None:
    """Rules exist only where a feed was found to carry several kinds.

    So on such a feed, matching none of them is not a fallback to a sensible
    default — it means the item was not recognised at all.
    """

    candidate = normalize_entry(
        make_nature_entry("https://www.nature.com/articles/unexpected-2026")
    )
    assert candidate.content_type_basis == "feed_unmatched"


def test_a_rule_matches_the_doi_when_the_url_does_not_carry_it() -> None:
    entry = make_nature_entry("https://www.nature.com/some/redirect")
    entry = entry.model_copy(
        update={"summary": "https://doi.org/10.1038/d41586-026-02311-z"}
    )
    assert normalize_entry(entry).content_type is ContentType.NEWS
