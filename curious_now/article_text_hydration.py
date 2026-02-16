"""Full-text hydration for non-paper items (news, press releases, reports, blogs).

Modeled on paper_text_hydration but much simpler — articles only need to fetch
the canonical URL and extract text via trafilatura (no arXiv/DOI/Unpaywall chains).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row

from curious_now.extractors.article_sources import (
    extract_article_text,
    is_article_quality_sufficient,
)
from curious_now.paper_text_hydration import (
    _batch_update_item_hydration,
    _http_get,
    _throttle_domain,
)

logger = logging.getLogger(__name__)

_PAPER_CONTENT_TYPES = ("preprint", "peer_reviewed")
_PAYWALL_STATUS_CODES = {401, 402, 403}


@dataclass(frozen=True)
class HydrateArticleTextResult:
    items_scanned: int
    items_hydrated: int
    items_failed: int
    items_skipped: int


def _get_articles_needing_hydration(
    conn: psycopg.Connection[Any],
    *,
    limit: int,
    item_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Get non-paper items that need full-text hydration."""
    params: list[Any] = []
    where_item_ids = ""
    if item_ids:
        placeholders = ",".join(["%s"] * len(item_ids))
        where_item_ids = f"AND i.id IN ({placeholders})"
        params.extend(item_ids)
    params.append(limit)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT
              i.id AS item_id,
              i.url,
              i.canonical_url,
              i.content_type,
              i.full_text,
              i.full_text_status
            FROM items i
            WHERE i.content_type NOT IN ('preprint', 'peer_reviewed')
              AND i.full_text_status = 'pending'
              AND (i.full_text IS NULL OR btrim(i.full_text) = '')
              {where_item_ids}
            ORDER BY i.published_at DESC NULLS LAST, i.fetched_at DESC
            LIMIT %s;
            """,
            tuple(params),
        )
        return cur.fetchall()


def _extract_article_text_for_item(
    item: dict[str, Any],
) -> tuple[str | None, str, str | None]:
    """Fetch canonical URL and extract article text.

    Returns:
        (text, status, source) where status is 'ok', 'paywalled', 'error', etc.
    """
    url = item.get("canonical_url") or item.get("url")
    if not url:
        return None, "error", None

    _throttle_domain(url)

    try:
        resp = _http_get(url, timeout_s=15.0)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("HTTP fetch failed for %s: %s", url, exc)
        return None, "error", None

    if resp.status_code in _PAYWALL_STATUS_CODES:
        return None, "paywalled", None

    if resp.status_code != 200:
        logger.info("HTTP %d for %s, marking as error", resp.status_code, url)
        return None, "error", None

    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return None, "error", None

    text = extract_article_text(resp.text, url=url)
    if not is_article_quality_sufficient(text):
        return None, "not_found", None

    return text, "ok", "article_url"


def hydrate_article_text(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 200,
    item_ids: list[UUID] | None = None,
    now_utc: datetime | None = None,
) -> HydrateArticleTextResult:
    """Hydrate full text for non-paper items by fetching their canonical URLs."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    items = _get_articles_needing_hydration(conn, limit=limit, item_ids=item_ids)
    hydrated = 0
    failed = 0
    skipped = 0
    pending_updates: list[dict[str, Any]] = []

    for item in items:
        item_id = UUID(str(item["item_id"]))
        content_type = str(item.get("content_type") or "")
        if content_type in _PAPER_CONTENT_TYPES:
            skipped += 1
            continue
        try:
            text, status, source = _extract_article_text_for_item(item)
            if text:
                hydrated += 1
            else:
                failed += 1
            pending_updates.append({
                "item_id": item_id,
                "full_text": text,
                "status": "ok" if text else status,
                "source": source,
                "kind": "fulltext" if text else None,
                "license_name": None,
                "image_url": None,
                "error_message": None,
                "now_utc": now_utc,
            })
        except Exception as exc:
            failed += 1
            logger.warning("Article text hydration failed for item %s: %s", item_id, exc)
            pending_updates.append({
                "item_id": item_id,
                "full_text": None,
                "status": "error",
                "source": None,
                "kind": None,
                "license_name": None,
                "image_url": None,
                "error_message": str(exc)[:4000],
                "now_utc": now_utc,
            })

    # Batch update all hydration results
    _batch_update_item_hydration(conn, pending_updates)

    return HydrateArticleTextResult(
        items_scanned=len(items),
        items_hydrated=hydrated,
        items_failed=failed,
        items_skipped=skipped,
    )
