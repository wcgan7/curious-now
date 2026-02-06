from __future__ import annotations

import hashlib
import html
import re
import time
from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import feedparser
import httpx
import psycopg
from dateutil import parser as dt_parser

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "cmpid",
    "icid",
    "ocid",
}

_ARXIV_NEW_RE = re.compile(r"\b\d{4}\.\d{4,5}(v\d+)?\b", re.IGNORECASE)
_ARXIV_OLD_RE = re.compile(r"\b[a-z-]+/\d{7}(v\d+)?\b", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


@dataclass(frozen=True)
class IngestResult:
    feeds_attempted: int
    feeds_succeeded: int
    items_seen: int
    items_inserted: int
    items_updated: int


@dataclass(frozen=True)
class FeedToFetch:
    feed_id: UUID
    source_id: UUID
    feed_url: str
    fetch_interval_minutes: int
    source_type: str


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_title_for_hash(title: str) -> str:
    return " ".join(title.strip().lower().split())


def normalize_url(url: str) -> str:
    """
    URL normalization v0 (see design_docs/url_normalization_v0.md).

    This is used to compute the idempotency key:
      canonical_hash = sha256(normalized_canonical_url)
    """
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if "@" in netloc:
        # Drop credentials if present.
        netloc = netloc.split("@", 1)[1]

    # Normalize default ports.
    host, sep, port = netloc.partition(":")
    if sep and port:
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    # Collapse duplicate slashes in path.
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    # Remove trailing slash only when path is not "/".
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # Normalize query params: remove tracking keys, sort remaining.
    q_in = parse_qsl(parts.query, keep_blank_values=True)
    q_out: list[tuple[str, str]] = []
    for k, v in q_in:
        key = k.strip()
        low = key.lower()
        if any(low.startswith(p) for p in _TRACKING_PARAM_PREFIXES):
            continue
        if low in _TRACKING_PARAMS:
            continue
        q_out.append((key, v))
    q_out.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(q_out, doseq=True)

    # Drop fragment.
    fragment = ""
    return urlunsplit((scheme, netloc, path, query, fragment))


def _guess_content_type(source_type: str) -> str:
    # Stage 1 content_type mapping v0 (source-based defaults).
    # See design_docs/stage1.md §10.3 and design_docs/decisions.md.
    st = (source_type or "").strip().lower()
    if st == "preprint_server":
        return "preprint"
    if st == "journal":
        return "peer_reviewed"
    if st == "government":
        return "report"
    if st in {"university", "lab"}:
        return "press_release"
    return "news"


def _extract_ids(text: str) -> tuple[str | None, str | None]:
    arxiv = None
    doi = None
    if m := _ARXIV_NEW_RE.search(text):
        arxiv = m.group(0)
    elif m := _ARXIV_OLD_RE.search(text):
        arxiv = m.group(0)
    if m := _DOI_RE.search(text):
        doi = m.group(0)
    return arxiv, doi


def _parse_published_at(entry: Any) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if st is not None:
        try:
            return datetime.fromtimestamp(timegm(st), tz=timezone.utc)
        except Exception:
            return None
    raw = entry.get("published") or entry.get("updated")
    if isinstance(raw, str) and raw.strip():
        try:
            dt = dt_parser.parse(raw)
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _pick_entry_url(entry: Any) -> str | None:
    link = entry.get("link")
    if isinstance(link, str) and link.strip():
        return link.strip()
    links = entry.get("links")
    if isinstance(links, list):
        for link_obj in links:
            if not isinstance(link_obj, dict):
                continue
            href = link_obj.get("href")
            rel = (link_obj.get("rel") or "").lower()
            if rel in {"alternate", ""} and isinstance(href, str) and href.strip():
                return href.strip()
    return None


def _strip_html(text: str) -> str:
    # Keep this intentionally simple (feeds often contain small HTML fragments).
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _get_entry_snippet(entry: Any, *, max_len: int = 500) -> str | None:
    raw = entry.get("summary") or entry.get("description")
    if not isinstance(raw, str):
        return None
    s = " ".join(_strip_html(raw).split())
    if not s:
        return None
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _list_feeds_to_fetch(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime,
    feed_id: UUID | None,
    limit: int,
    force: bool,
) -> list[FeedToFetch]:
    due_sql = ""
    params: list[Any] = []
    if feed_id is not None:
        due_sql = "AND f.id = %s"
        params.append(feed_id)
    elif not force:
        due_sql = (
            "AND (f.last_fetched_at IS NULL OR "
            "f.last_fetched_at + (f.fetch_interval_minutes || ' minutes')::interval <= %s)"
        )
        params.append(now_utc)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              f.id AS feed_id,
              f.source_id,
              f.feed_url,
              f.fetch_interval_minutes,
              s.source_type
            FROM source_feeds f
            JOIN sources s ON s.id = f.source_id
            WHERE f.active = true
              AND s.active = true
              {due_sql}
            ORDER BY COALESCE(f.last_fetched_at, 'epoch'::timestamptz) ASC
            LIMIT %s;
            """,
            (*params, limit),
        )
        rows = cur.fetchall()

    out: list[FeedToFetch] = []
    for r in rows:
        out.append(
            FeedToFetch(
                feed_id=UUID(str(_row_get(r, "feed_id", 0))),
                source_id=UUID(str(_row_get(r, "source_id", 1))),
                feed_url=str(_row_get(r, "feed_url", 2)),
                fetch_interval_minutes=int(_row_get(r, "fetch_interval_minutes", 3)),
                source_type=str(_row_get(r, "source_type", 4)),
            )
        )
    return out


def _mark_feed_result(
    conn: psycopg.Connection[Any],
    *,
    feed_id: UUID,
    now_utc: datetime,
    ok: bool,
    http_status: int | None,
    error_message: str | None,
) -> None:
    with conn.cursor() as cur:
        if ok:
            cur.execute(
                """
                UPDATE source_feeds
                SET last_fetched_at = %s,
                    last_status = %s,
                    error_streak = 0
                WHERE id = %s;
                """,
                (now_utc, http_status, feed_id),
            )
        else:
            cur.execute(
                """
                UPDATE source_feeds
                SET last_fetched_at = %s,
                    last_status = %s,
                    error_streak = error_streak + 1
                WHERE id = %s;
                """,
                (now_utc, http_status, feed_id),
            )


def _insert_fetch_log(
    conn: psycopg.Connection[Any],
    *,
    feed_id: UUID,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    http_status: int | None,
    duration_ms: int | None,
    error_message: str | None,
    items_seen: int,
    items_upserted: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feed_fetch_logs(
              feed_id,
              started_at,
              finished_at,
              status,
              http_status,
              duration_ms,
              error_message,
              items_seen,
              items_upserted
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                feed_id,
                started_at,
                finished_at,
                status,
                http_status,
                duration_ms,
                error_message,
                items_seen,
                items_upserted,
            ),
        )


def _upsert_item(
    conn: psycopg.Connection[Any],
    *,
    source_id: UUID,
    url: str,
    canonical_url: str,
    title: str,
    published_at: datetime | None,
    author: str | None,
    snippet: str | None,
    content_type: str,
    arxiv_id: str | None,
    doi: str | None,
    now_utc: datetime,
) -> tuple[bool, bool]:
    canonical_hash = _sha256_hex(canonical_url)
    title_hash = _sha256_hex(normalize_title_for_hash(title))
    full_text_status = "pending" if content_type in {"preprint", "peer_reviewed"} else None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO items(
              source_id,
              url,
              canonical_url,
              title,
              published_at,
              fetched_at,
              author,
              snippet,
              content_type,
              language,
              title_hash,
              canonical_hash,
              arxiv_id,
              doi,
              full_text_status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'en',%s,%s,%s,%s,%s)
            ON CONFLICT (canonical_hash)
            DO UPDATE SET
              url = EXCLUDED.url,
              canonical_url = EXCLUDED.canonical_url,
              title = EXCLUDED.title,
              published_at = COALESCE(items.published_at, EXCLUDED.published_at),
              fetched_at = EXCLUDED.fetched_at,
              author = COALESCE(items.author, EXCLUDED.author),
              snippet = COALESCE(items.snippet, EXCLUDED.snippet),
              content_type = EXCLUDED.content_type,
              title_hash = EXCLUDED.title_hash,
              arxiv_id = COALESCE(items.arxiv_id, EXCLUDED.arxiv_id),
              doi = COALESCE(items.doi, EXCLUDED.doi),
              full_text_status = CASE
                WHEN items.full_text IS NOT NULL AND btrim(items.full_text) <> '' THEN 'ok'
                WHEN EXCLUDED.content_type IN ('preprint', 'peer_reviewed')
                  THEN COALESCE(items.full_text_status, EXCLUDED.full_text_status, 'pending')
                ELSE items.full_text_status
              END
            RETURNING (xmax = 0) AS inserted;
            """,
            (
                source_id,
                url,
                canonical_url,
                title,
                published_at,
                now_utc,
                author,
                snippet,
                content_type,
                title_hash,
                canonical_hash,
                arxiv_id,
                doi,
                full_text_status,
            ),
        )
        row = cur.fetchone()

    inserted = bool(_row_get(row, "inserted", 0)) if row else False
    return inserted, not inserted


def _fetch_feed(url: str) -> httpx.Response:
    headers = {"User-Agent": "CuriousNow/0.1 (+feed-fetcher)"}
    timeout = httpx.Timeout(10.0, connect=5.0)
    backoff_s = 1.0
    for attempt in range(3):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                resp = client.get(url)
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
            return resp
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == 2:
                raise exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 or attempt == 2:
                raise
        time.sleep(backoff_s)
        backoff_s *= 2
    raise RuntimeError("unreachable")


def ingest_due_feeds(
    conn: psycopg.Connection[Any],
    *,
    now_utc: datetime | None = None,
    feed_id: UUID | None = None,
    limit_feeds: int = 25,
    max_items_per_feed: int = 200,
    force: bool = False,
) -> IngestResult:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    feeds = _list_feeds_to_fetch(conn, now_utc=now, feed_id=feed_id, limit=limit_feeds, force=force)

    feeds_attempted = 0
    feeds_succeeded = 0
    total_seen = 0
    total_inserted = 0
    total_updated = 0

    for f in feeds:
        feeds_attempted += 1
        started_at = datetime.now(timezone.utc)
        http_status: int | None = None
        error_message: str | None = None

        try:
            resp = _fetch_feed(f.feed_url)
            http_status = int(resp.status_code)
            resp.raise_for_status()

            parsed = feedparser.parse(resp.content)
            entries = parsed.get("entries") or []
            if not isinstance(entries, list):
                entries = []

            seen = 0
            inserted = 0
            updated = 0

            for e in entries[: max_items_per_feed]:
                if not isinstance(e, dict):
                    continue
                title_raw = e.get("title")
                if not isinstance(title_raw, str) or not title_raw.strip():
                    continue
                url_raw = _pick_entry_url(e)
                if not url_raw:
                    continue

                url = url_raw.strip()
                canonical_url = normalize_url(url)
                title = " ".join(title_raw.split())
                published_at = _parse_published_at(e)
                author = e.get("author") if isinstance(e.get("author"), str) else None
                snippet = _get_entry_snippet(e)
                content_type = _guess_content_type(f.source_type)

                arxiv_id, doi = _extract_ids(f"{title} {url}")

                ins, upd = _upsert_item(
                    conn,
                    source_id=f.source_id,
                    url=url,
                    canonical_url=canonical_url,
                    title=title,
                    published_at=published_at,
                    author=author,
                    snippet=snippet,
                    content_type=content_type,
                    arxiv_id=arxiv_id,
                    doi=doi,
                    now_utc=now,
                )
                seen += 1
                inserted += 1 if ins else 0
                updated += 1 if upd else 0

            finished_at = datetime.now(timezone.utc)
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)

            _mark_feed_result(
                conn,
                feed_id=f.feed_id,
                now_utc=now,
                ok=True,
                http_status=http_status,
                error_message=None,
            )
            _insert_fetch_log(
                conn,
                feed_id=f.feed_id,
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                http_status=http_status,
                duration_ms=duration_ms,
                error_message=None,
                items_seen=seen,
                items_upserted=(inserted + updated),
            )

            feeds_succeeded += 1
            total_seen += seen
            total_inserted += inserted
            total_updated += updated
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            finished_at = datetime.now(timezone.utc)
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)

            _mark_feed_result(
                conn,
                feed_id=f.feed_id,
                now_utc=now,
                ok=False,
                http_status=http_status,
                error_message=error_message,
            )
            _insert_fetch_log(
                conn,
                feed_id=f.feed_id,
                started_at=started_at,
                finished_at=finished_at,
                status="error",
                http_status=http_status,
                duration_ms=duration_ms,
                error_message=error_message,
                items_seen=0,
                items_upserted=0,
            )

    return IngestResult(
        feeds_attempted=feeds_attempted,
        feeds_succeeded=feeds_succeeded,
        items_seen=total_seen,
        items_inserted=total_inserted,
        items_updated=total_updated,
    )
