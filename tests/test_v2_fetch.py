from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from curious_now_v2.retrieval.fetch import (
    MAX_BODY_BYTES,
    Fetcher,
    FetchOutcome,
    RobotsCache,
)

Handler = Callable[[httpx.Request], httpx.Response]


def build_fetcher(handler: Handler, **kwargs: object) -> Fetcher:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True)
    # sleep=False keeps pacing logic exercised without real delays.
    return Fetcher(client=client, sleep=False, **kwargs)  # type: ignore[arg-type]


def permissive_robots(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    return None


def test_successful_fetch_returns_body_and_validators() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(
            200,
            content=b"<html>paper</html>",
            headers={
                "content-type": "text/html; charset=utf-8",
                "etag": 'W/"abc"',
                "last-modified": "Wed, 29 Jul 2026 10:00:00 GMT",
            },
        )

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/paper")

    assert result.outcome is FetchOutcome.OK
    assert result.text() == "<html>paper</html>"
    assert result.etag == 'W/"abc"'
    assert result.last_modified == "Wed, 29 Jul 2026 10:00:00 GMT"


def test_robots_disallow_prevents_the_request() -> None:
    attempted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        attempted.append(str(request.url))
        return httpx.Response(200, content=b"secret")

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/private/paper")

    assert result.outcome is FetchOutcome.BLOCKED_BY_ROBOTS
    assert attempted == []


def test_unreachable_robots_is_treated_as_permissive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            raise httpx.ConnectError("no robots", request=request)
        return httpx.Response(200, content=b"body")

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/article")

    assert result.outcome is FetchOutcome.OK


def test_robots_rules_are_cached_across_requests() -> None:
    robots_hits = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal robots_hits
        if request.url.path == "/robots.txt":
            robots_hits += 1
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, content=b"body")

    with build_fetcher(handler) as fetcher:
        for index in range(3):
            fetcher.fetch(f"https://example.test/a{index}")

    assert robots_hits == 1


def test_paywalled_status_is_reported_and_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        calls += 1
        return httpx.Response(403)

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/paywalled")

    assert result.outcome is FetchOutcome.PAYWALLED
    assert calls == 1


def test_not_modified_short_circuits_a_conditional_request() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        seen.update(request.headers)
        return httpx.Response(304)

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch(
            "https://example.test/paper",
            etag='W/"abc"',
            last_modified="Wed, 29 Jul 2026 10:00:00 GMT",
        )

    assert result.outcome is FetchOutcome.NOT_MODIFIED
    assert seen["if-none-match"] == 'W/"abc"'
    assert seen["if-modified-since"] == "Wed, 29 Jul 2026 10:00:00 GMT"


def test_rate_limit_is_retried_then_succeeds() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, content=b"body")

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/paper")

    assert result.outcome is FetchOutcome.OK
    assert attempts == 2


def test_server_errors_are_retried_up_to_the_attempt_limit() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        attempts += 1
        return httpx.Response(503)

    with build_fetcher(handler, max_attempts=3) as fetcher:
        result = fetcher.fetch("https://example.test/paper")

    assert result.outcome is FetchOutcome.ERROR
    assert attempts == 3


def test_network_errors_are_retried_and_reported() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        attempts += 1
        raise httpx.ReadTimeout("slow", request=request)

    with build_fetcher(handler, max_attempts=2) as fetcher:
        result = fetcher.fetch("https://example.test/paper")

    assert result.outcome is FetchOutcome.ERROR
    assert result.error is not None
    assert "ReadTimeout" in result.error
    assert attempts == 2


def test_oversized_body_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(200, content=b"x" * (MAX_BODY_BYTES + 1))

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/huge.pdf")

    assert result.outcome is FetchOutcome.TOO_LARGE


def test_missing_resource_is_distinguished_from_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(404)

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/gone")

    assert result.outcome is FetchOutcome.NOT_FOUND


def test_pdf_is_detected_by_magic_bytes_when_content_type_lies() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(
            200,
            content=b"%PDF-1.7\ncontent",
            headers={"content-type": "application/octet-stream"},
        )

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/paper.pdf")

    assert result.is_pdf is True


def test_declared_charset_is_used_to_decode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(
            200,
            content="café".encode("latin-1"),
            headers={"content-type": "text/html; charset=latin-1"},
        )

    with build_fetcher(handler) as fetcher:
        result = fetcher.fetch("https://example.test/article")

    assert result.text() == "café"


@pytest.mark.parametrize(
    ("robots_body", "expected"),
    [
        ("User-agent: *\nAllow: /\n", 1.0),
        ("User-agent: *\nCrawl-delay: 5\nAllow: /\n", 5.0),
        # A hostile crawl-delay must not stall the pipeline indefinitely.
        ("User-agent: *\nCrawl-delay: 9999\nAllow: /\n", 30.0),
    ],
)
def test_crawl_delay_respects_the_site_within_bounds(
    robots_body: str,
    expected: float,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=robots_body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cache = RobotsCache()

    assert cache.crawl_delay(client, "https://example.test/paper") == expected


def test_pacing_is_tracked_per_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = permissive_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(200, content=b"body")

    with build_fetcher(handler) as fetcher:
        fetcher.fetch("https://a.test/one")
        fetcher.fetch("https://b.test/one")

        assert set(fetcher._domains) == {"a.test", "b.test"}
