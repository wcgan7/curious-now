from __future__ import annotations

from uuid import uuid4

import httpx

from curious_now_v2.core.enums import ContentType, SourceRole
from curious_now_v2.core.source_registry import FeedSpec, SourcePolicy, SourceSpec
from curious_now_v2.pipeline.feed_reader import (
    FeedReadStatus,
    fetch_feed,
)

RSS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Science</title>
    <item>
      <guid>paper-42</guid>
      <title>A &amp; B in science</title>
      <link>https://example.test/paper/?utm_source=rss</link>
      <description><![CDATA[<p>A <strong>clear</strong> summary.</p>]]></description>
      <pubDate>Sun, 26 Jul 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <guid isPermaLink="false">missing-link</guid>
      <title>This entry is incomplete</title>
    </item>
  </channel>
</rss>
"""


def make_source() -> tuple[SourceSpec, FeedSpec]:
    feed = FeedSpec(
        url="https://example.test/feed.xml",
        default_content_type=ContentType.PEER_REVIEWED,
    )
    source = SourceSpec(
        name="Example Science",
        role=SourceRole.PRIMARY_RESEARCH,
        feeds=(feed,),
        policy=SourcePolicy(counts_as_independent=False),
    )
    return source, feed


def test_fetch_feed_uses_cache_headers_and_normalizes_entries() -> None:
    seen_headers: httpx.Headers | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_headers
        seen_headers = request.headers
        return httpx.Response(
            200,
            content=RSS,
            headers={
                "content-type": "application/rss+xml",
                "etag": '"new-etag"',
                "last-modified": "Sun, 26 Jul 2026 08:00:00 GMT",
            },
        )

    source, feed = make_source()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = fetch_feed(
            client=client,
            source_id=uuid4(),
            source=source,
            feed=feed,
            etag='"old-etag"',
        )

    assert seen_headers is not None
    assert seen_headers["if-none-match"] == '"old-etag"'
    assert batch.status is FeedReadStatus.SUCCEEDED
    assert batch.etag == '"new-etag"'
    assert batch.skipped_entries == 1
    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert candidate.source_native_id == "paper-42"
    assert candidate.title == "A & B in science"
    assert candidate.canonical_url == "https://example.test/paper"
    assert candidate.snippet == "A clear summary."
    assert candidate.published_at is not None


def test_fetch_feed_treats_not_modified_as_a_successful_empty_batch() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(304)

    source, feed = make_source()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = fetch_feed(
            client=client,
            source_id=uuid4(),
            source=source,
            feed=feed,
            etag='"same-etag"',
        )

    assert batch.status is FeedReadStatus.NOT_MODIFIED
    assert batch.candidates == ()
    assert batch.etag == '"same-etag"'


MIXED_RSS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Broadcaster Science</title>
    <item>
      <guid>article-1</guid>
      <title>How a fire builds its own thunderstorm</title>
      <link>https://example.test/news/articles/c8r2074l0rmo</link>
    </item>
    <item>
      <guid>schedule-1</guid>
      <title>Inside Science</title>
      <link>https://example.test/sounds/play/live:radio_four</link>
    </item>
    <item>
      <guid>video-1</guid>
      <title>Drone footage shows tornado damage</title>
      <link>https://example.test/news/videos/cgr751pvnd2o</link>
    </item>
  </channel>
</rss>
"""


def test_a_feed_may_carry_entries_that_are_not_readable_items() -> None:
    """Some feed entries have nothing behind them to read.

    A broadcaster's science feed includes its live radio schedule, whose text
    is whatever is on air and different every hour, and video pages with no
    transcript. Both were ingested, fetched, retried fortnightly, and — where
    they had enough words — classified by a model before being withheld.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=MIXED_RSS,
                              headers={"content-type": "application/rss+xml"})

    feed = FeedSpec(
        url="https://example.test/feed.xml",
        default_content_type=ContentType.NEWS,
        exclude_patterns=("/sounds/play", "/news/videos"),
    )
    source = SourceSpec(
        name="Broadcaster Science",
        role=SourceRole.JOURNALISM,
        feeds=(feed,),
        policy=SourcePolicy(counts_as_independent=True),
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = fetch_feed(
            client=client, source_id=uuid4(), source=source, feed=feed
        )

    assert len(batch.candidates) == 1
    assert batch.candidates[0].url.endswith("c8r2074l0rmo")
    assert batch.skipped_entries == 2


def test_an_unconfigured_feed_excludes_nothing() -> None:
    feed = FeedSpec(
        url="https://example.test/feed.xml",
        default_content_type=ContentType.NEWS,
    )
    assert feed.excludes("https://example.test/sounds/play/anything") is None
