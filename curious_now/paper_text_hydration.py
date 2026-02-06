from __future__ import annotations

import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import psycopg

logger = logging.getLogger(__name__)

_PAPER_CONTENT_TYPES = ("preprint", "peer_reviewed")
_MAX_FULL_TEXT_CHARS = 120_000


@dataclass(frozen=True)
class HydratePaperTextResult:
    items_scanned: int
    items_hydrated: int
    items_failed: int
    items_skipped: int


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:_MAX_FULL_TEXT_CHARS]


def _reconstruct_openalex_abstract(inverted_index: dict[str, list[int]]) -> str | None:
    if not inverted_index:
        return None
    pairs: list[tuple[int, str]] = []
    for token, positions in inverted_index.items():
        for pos in positions:
            pairs.append((int(pos), token))
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])
    text = " ".join(token for _, token in pairs)
    return _clean_text(text)


def _http_get(url: str, *, timeout_s: float = 12.0) -> httpx.Response:
    headers = {"User-Agent": "CuriousNow/0.1 (+paper-text-hydration)"}
    timeout = httpx.Timeout(timeout_s, connect=5.0)
    backoff_s = 1.0
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                return client.get(url)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt == 2:
                raise
            time.sleep(backoff_s)
            backoff_s *= 2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


def _fetch_arxiv_abstract(arxiv_id: str) -> str | None:
    url = f"https://export.arxiv.org/api/query?id_list={quote(arxiv_id)}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return None
    try:
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        summary = entry.find("atom:summary", ns)
        text = summary.text if summary is not None else None
        return _clean_text(text)
    except ET.ParseError:
        return None


def _fetch_crossref_abstract(doi: str) -> str | None:
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    message = data.get("message", {}) if isinstance(data, dict) else {}
    return _clean_text(message.get("abstract"))


def _fetch_openalex_abstract(doi: str) -> str | None:
    url = f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='')}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    inv = data.get("abstract_inverted_index")
    if not isinstance(inv, dict):
        return None
    casted: dict[str, list[int]] = {}
    for k, v in inv.items():
        if isinstance(k, str) and isinstance(v, list):
            casted[k] = [int(x) for x in v if isinstance(x, int)]
    return _reconstruct_openalex_abstract(casted)


def _fetch_landing_page_text(url: str) -> tuple[str | None, str]:
    resp = _http_get(url)
    if resp.status_code in (401, 402, 403):
        return None, "paywalled"
    if resp.status_code != 200:
        return None, "not_found"
    text = _clean_text(resp.text)
    if not text:
        return None, "not_found"
    if len(text) < 800:
        return None, "not_found"
    return text, "ok"


def _extract_item_text(item: dict[str, Any]) -> tuple[str | None, str, str | None]:
    arxiv_id = item.get("arxiv_id")
    doi = item.get("doi")
    url = item.get("url")
    canonical_url = item.get("canonical_url")

    if isinstance(arxiv_id, str) and arxiv_id.strip():
        text = _fetch_arxiv_abstract(arxiv_id.strip())
        if text:
            return text, "ok", "arxiv_api"

    if isinstance(doi, str) and doi.strip():
        text = _fetch_crossref_abstract(doi.strip())
        if text:
            return text, "ok", "crossref"
        text = _fetch_openalex_abstract(doi.strip())
        if text:
            return text, "ok", "openalex"

    landing = canonical_url if isinstance(canonical_url, str) and canonical_url else url
    if isinstance(landing, str) and landing:
        text, status = _fetch_landing_page_text(landing)
        if text:
            return text, "ok", "landing_page"
        return None, status, "landing_page"

    return None, "not_found", None


def _get_items_needing_hydration(
    conn: psycopg.Connection[Any],
    *,
    limit: int,
    item_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    where_item_ids = ""
    params: list[Any] = []
    if item_ids:
        where_item_ids = "AND i.id = ANY(%s::uuid[])"
        params.append([str(x) for x in item_ids])
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              i.id AS item_id,
              i.url,
              i.canonical_url,
              i.arxiv_id,
              i.doi,
              i.content_type,
              i.full_text,
              i.full_text_status
            FROM items i
            WHERE i.content_type IN ('preprint', 'peer_reviewed')
              AND (i.full_text IS NULL OR btrim(i.full_text) = '')
              {where_item_ids}
            ORDER BY i.published_at DESC NULLS LAST, i.fetched_at DESC
            LIMIT %s;
            """,
            tuple(params),
        )
        return cur.fetchall()


def _update_item_hydration(
    conn: psycopg.Connection[Any],
    *,
    item_id: UUID,
    full_text: str | None,
    status: str,
    source: str | None,
    error_message: str | None,
    now_utc: datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE items
            SET full_text = %s,
                full_text_status = %s,
                full_text_source = %s,
                full_text_error = %s,
                full_text_fetched_at = %s,
                updated_at = now()
            WHERE id = %s;
            """,
            (full_text, status, source, error_message, now_utc, item_id),
        )


def hydrate_paper_text(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 100,
    item_ids: list[UUID] | None = None,
    now_utc: datetime | None = None,
) -> HydratePaperTextResult:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    items = _get_items_needing_hydration(conn, limit=limit, item_ids=item_ids)
    hydrated = 0
    failed = 0
    skipped = 0

    for item in items:
        item_id = UUID(str(item["item_id"]))
        content_type = str(item.get("content_type") or "")
        if content_type not in _PAPER_CONTENT_TYPES:
            skipped += 1
            continue
        try:
            text, status, source = _extract_item_text(item)
            if text:
                hydrated += 1
                _update_item_hydration(
                    conn,
                    item_id=item_id,
                    full_text=text,
                    status="ok",
                    source=source,
                    error_message=None,
                    now_utc=now_utc,
                )
            else:
                failed += 1
                _update_item_hydration(
                    conn,
                    item_id=item_id,
                    full_text=None,
                    status=status,
                    source=source,
                    error_message=None,
                    now_utc=now_utc,
                )
        except Exception as exc:
            failed += 1
            logger.warning("Paper text hydration failed for item %s: %s", item_id, exc)
            _update_item_hydration(
                conn,
                item_id=item_id,
                full_text=None,
                status="error",
                source=None,
                error_message=str(exc)[:4000],
                now_utc=now_utc,
            )

    return HydratePaperTextResult(
        items_scanned=len(items),
        items_hydrated=hydrated,
        items_failed=failed,
        items_skipped=skipped,
    )
