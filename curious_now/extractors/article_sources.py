"""Extraction for non-paper article sources (news, press releases, reports, blogs).

Uses trafilatura for high-quality article body extraction with a BeautifulSoup
fallback.  Quality gates are relaxed compared to paper_sources — no academic
section keywords required.
"""

from __future__ import annotations

import html as html_mod
import re

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_MAX_ARTICLE_CHARS = 120_000
_MIN_QUALITY_CHARS = 500
_MIN_QUALITY_WORDS = 100


def extract_article_text(raw_html: str, *, url: str | None = None) -> str | None:
    """Extract article body text from raw HTML.

    Primary: trafilatura with ``favor_recall=True``.
    Fallback: BeautifulSoup-based ``extract_html_body_text`` from paper_sources.
    """
    text = _trafilatura_extract(raw_html, url=url)
    if not text or len(text) < _MIN_QUALITY_CHARS:
        text = _bs4_fallback(raw_html)
    if not text:
        return None
    text = _clean_article_text(text)
    if not text:
        return None
    return text[:_MAX_ARTICLE_CHARS]


def is_article_quality_sufficient(text: str | None) -> bool:
    """Check whether extracted article text meets minimum quality thresholds.

    Unlike paper quality gates, this does NOT require academic section keywords
    (introduction, methods, results, etc.) — news articles would never pass that.
    """
    if not text:
        return False
    if len(text) < _MIN_QUALITY_CHARS:
        return False
    if len(text.split()) < _MIN_QUALITY_WORDS:
        return False
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _trafilatura_extract(raw_html: str, *, url: str | None = None) -> str | None:
    try:
        import trafilatura

        result = trafilatura.extract(
            raw_html,
            url=url,
            favor_recall=True,
            include_comments=False,
            include_tables=False,
            deduplicate=True,
        )
        return result if result else None
    except Exception:
        return None


def _bs4_fallback(raw_html: str) -> str | None:
    """Lightweight BeautifulSoup extraction — same logic as paper_sources."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
            tag.decompose()
        for selector in ("nav", "header", "footer", "aside"):
            for node in soup.select(selector):
                node.decompose()
        for img in soup.find_all("img"):
            img.decompose()
        text = soup.get_text("\n")
        return text.strip() if text else None
    except Exception:
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "\n", text)
        return text.strip() if text else None


def _clean_article_text(text: str) -> str:
    """Light text cleaning: HTML unescape, whitespace normalization."""
    text = html_mod.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()
