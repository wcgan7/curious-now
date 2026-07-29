from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "CuriousNow/2 (+https://github.com/curious-now)"

# Politeness defaults. A site's own crawl-delay always wins when it is larger.
DEFAULT_CRAWL_DELAY_SECONDS = 1.0
MAX_CRAWL_DELAY_SECONDS = 30.0
ROBOTS_TTL_SECONDS = 3600.0

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 60.0

# A pathological PDF should not exhaust memory.
MAX_BODY_BYTES = 25 * 1024 * 1024

PAYWALL_STATUSES = frozenset({401, 402, 403})
MISSING_STATUSES = frozenset({404, 410})


class FetchOutcome(StrEnum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    PAYWALLED = "paywalled"
    NOT_FOUND = "not_found"
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    TOO_LARGE = "too_large"
    ERROR = "error"


@dataclass(frozen=True)
class FetchResult:
    url: str
    outcome: FetchOutcome
    status_code: int | None = None
    final_url: str | None = None
    body: bytes = b""
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is FetchOutcome.OK

    @property
    def is_pdf(self) -> bool:
        if self.content_type and "pdf" in self.content_type.casefold():
            return True
        return self.body[:5] == b"%PDF-"

    def text(self) -> str:
        """Decode the body, preferring the charset the server declared."""

        encoding = "utf-8"
        if self.content_type and "charset=" in self.content_type:
            encoding = self.content_type.split("charset=", 1)[1].split(";")[0].strip()
        try:
            return self.body.decode(encoding, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


class RobotsCache:
    """Per-origin robots.txt rules with a refresh interval.

    A robots.txt that cannot be fetched is treated as permissive, which is the
    conventional reading: absence of rules is not a prohibition. A robots.txt
    that is fetched and disallows a path is always honored.
    """

    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        ttl_seconds: float = ROBOTS_TTL_SECONDS,
    ) -> None:
        self._user_agent = user_agent
        self._ttl = ttl_seconds
        self._parsers: dict[str, tuple[RobotFileParser | None, float]] = {}

    def _load(self, client: httpx.Client, origin: str) -> RobotFileParser | None:
        try:
            response = client.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    def _parser(self, client: httpx.Client, origin: str) -> RobotFileParser | None:
        cached = self._parsers.get(origin)
        now = time.monotonic()
        if cached is not None and now - cached[1] < self._ttl:
            return cached[0]
        parser = self._load(client, origin)
        self._parsers[origin] = (parser, now)
        return parser

    def allows(self, client: httpx.Client, url: str) -> bool:
        parser = self._parser(client, _origin(url))
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)

    def crawl_delay(self, client: httpx.Client, url: str) -> float:
        parser = self._parser(client, _origin(url))
        if parser is None:
            return DEFAULT_CRAWL_DELAY_SECONDS
        try:
            declared = parser.crawl_delay(self._user_agent)
        except (AttributeError, ValueError):
            declared = None
        if declared is None:
            return DEFAULT_CRAWL_DELAY_SECONDS
        return min(max(float(declared), DEFAULT_CRAWL_DELAY_SECONDS), MAX_CRAWL_DELAY_SECONDS)


@dataclass
class _DomainState:
    next_allowed_at: float = 0.0


class Fetcher:
    """A polite HTTP client for retrieval.

    Improves on the v1 fetcher in the ways that matter for crawling many
    domains: one pooled client instead of a connection per request, robots.txt
    honored, per-domain pacing applied to every request including provider
    APIs, conditional GET, and retries that respect Retry-After.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        user_agent: str = USER_AGENT,
        robots: RobotsCache | None = None,
        sleep: bool = True,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        self._user_agent = user_agent
        self._robots = robots if robots is not None else RobotsCache(user_agent=user_agent)
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)
        self._domains: dict[str, _DomainState] = {}

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _pause(self, seconds: float) -> None:
        if self._sleep and seconds > 0:
            time.sleep(seconds)

    def _wait_for_domain(self, url: str) -> None:
        """Space out requests to one host, including provider APIs."""

        host = urlsplit(url).netloc
        state = self._domains.setdefault(host, _DomainState())
        now = time.monotonic()
        if state.next_allowed_at > now:
            self._pause(state.next_allowed_at - now)
        delay = self._robots.crawl_delay(self._client, url)
        state.next_allowed_at = time.monotonic() + delay

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if not raw:
            return None
        try:
            return min(max(float(raw), 0.0), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            # The header also permits an HTTP date; a fixed pause is a safe
            # reading when we cannot parse it.
            return BACKOFF_BASE_SECONDS

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        accept: str | None = None,
    ) -> FetchResult:
        """Fetch one URL, honoring robots.txt and per-domain pacing."""

        if not self._robots.allows(self._client, url):
            return FetchResult(
                url=url,
                outcome=FetchOutcome.BLOCKED_BY_ROBOTS,
                error="robots.txt disallows this path",
            )

        headers = {"User-Agent": self._user_agent}
        if accept:
            headers["Accept"] = accept
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        last_error: str | None = None
        for attempt in range(self._max_attempts):
            if attempt:
                self._pause(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            self._wait_for_domain(url)
            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue

            status = response.status_code
            if status == httpx.codes.NOT_MODIFIED:
                return FetchResult(
                    url=url,
                    outcome=FetchOutcome.NOT_MODIFIED,
                    status_code=status,
                    final_url=str(response.url),
                    etag=etag,
                    last_modified=last_modified,
                )
            if status in PAYWALL_STATUSES:
                return FetchResult(
                    url=url,
                    outcome=FetchOutcome.PAYWALLED,
                    status_code=status,
                    final_url=str(response.url),
                    error="access denied by the publisher",
                )
            if status in MISSING_STATUSES:
                return FetchResult(
                    url=url,
                    outcome=FetchOutcome.NOT_FOUND,
                    status_code=status,
                    final_url=str(response.url),
                )
            if status == httpx.codes.TOO_MANY_REQUESTS:
                last_error = "rate limited"
                self._pause(
                    self._retry_after_seconds(response)
                    or BACKOFF_BASE_SECONDS * (2**attempt)
                )
                continue
            if status >= 500:
                last_error = f"server error {status}"
                continue
            if status >= 400:
                return FetchResult(
                    url=url,
                    outcome=FetchOutcome.ERROR,
                    status_code=status,
                    final_url=str(response.url),
                    error=f"unexpected status {status}",
                )

            body = response.content
            if len(body) > MAX_BODY_BYTES:
                return FetchResult(
                    url=url,
                    outcome=FetchOutcome.TOO_LARGE,
                    status_code=status,
                    final_url=str(response.url),
                    error=f"body exceeds {MAX_BODY_BYTES} bytes",
                )
            return FetchResult(
                url=url,
                outcome=FetchOutcome.OK,
                status_code=status,
                final_url=str(response.url),
                body=body,
                content_type=response.headers.get("content-type"),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )

        return FetchResult(
            url=url,
            outcome=FetchOutcome.ERROR,
            error=last_error or "request failed",
        )
