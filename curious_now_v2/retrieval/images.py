"""Recover source-owned preview and figure image URLs.

Images remain on the publisher's servers.  This module records only URLs the
publisher itself marks as the article preview or as a figure in structured
JATS.  It deliberately does not fall back to the first ``<img>`` on a page:
for medRxiv that is a logo, and a repeated publisher logo is worse than an
honest imageless card.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

_PREVIEW_META = frozenset({"og:image", "twitter:image"})
_GENERIC_IMAGE_MARKERS = (
    "favicon",
    "logo",
    "loading.gif",
    "sprite",
    "avatar",
    "placeholder",
    "twitter.png",
    "facebook",
    "linkedin",
    "mendeley",
)
_ELIFE_ARTICLE = re.compile(r"elifesciences\.org/articles/(\d+)", re.I)
_PLOS_ARTICLE = re.compile(r"journals\.plos\.org/([^/]+)/article/", re.I)
_NPR_RESIZER_HOST = "npr.brightspotcdn.com"
_NPR_ASSET_HOST = "npr-brightspot.s3.amazonaws.com"
_UNSERVABLE_PREVIEW_HOSTS = frozenset({"physics.aps.org"})


def _http_url(value: str, *, base_url: str) -> str | None:
    resolved = urljoin(base_url, value.strip())
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return resolved


def _specific_preview(value: str, *, base_url: str) -> str | None:
    resolved = _http_url(value, base_url=base_url)
    if not resolved:
        return None
    parsed = urlsplit(resolved)
    if parsed.hostname in _UNSERVABLE_PREVIEW_HOSTS:
        # APS advertises these thumbnails in Open Graph, but its asset server
        # answers both direct requests and Next's image optimiser with a WAF
        # 403. An absent image is an intentional, complete card state; storing
        # a URL known to be unreachable only creates a broken one.
        return None
    if parsed.hostname == _NPR_RESIZER_HOST:
        # NPR declares a Brightspot resize URL, but that endpoint returns 403
        # to Next's server-side image optimiser. The URL itself carries the
        # source-owned S3 object in its `url` parameter. Unwrap only NPR's exact
        # bucket (never an arbitrary nested URL) and force HTTPS so the image a
        # publisher selected is also one the reader can actually serve.
        nested = parse_qs(parsed.query).get("url", ())
        if not nested:
            return None
        asset = urlsplit(nested[0])
        if asset.netloc.casefold() != _NPR_ASSET_HOST:
            return None
        resolved = urlunsplit(
            ("https", _NPR_ASSET_HOST, asset.path, asset.query, "")
        )
    folded = resolved.casefold()
    if any(marker in folded for marker in _GENERIC_IMAGE_MARKERS):
        return None
    return resolved


def extract_html_preview_image(html: str, *, base_url: str) -> str | None:
    """The article-specific preview declared in HTML metadata, if any."""

    soup = BeautifulSoup(html, "html.parser")
    for node in soup.find_all("meta"):
        key = str(node.get("property") or node.get("name") or "").casefold()
        content = node.get("content")
        if key in _PREVIEW_META and isinstance(content, str):
            if resolved := _specific_preview(content, base_url=base_url):
                return resolved

    # ``image_src`` predates Open Graph but is still used by some journals.
    for node in soup.find_all("link"):
        rel = node.get("rel") or ()
        relations = {str(value).casefold() for value in rel}
        href = node.get("href")
        if "image_src" in relations and isinstance(href, str):
            if resolved := _specific_preview(href, base_url=base_url):
                return resolved
    return None


def jats_figure_image(
    figure: Tag,
    *,
    source: str | None,
    base_url: str | None,
) -> str | None:
    """Resolve the first static image attached to one JATS ``<fig>``.

    JATS standardises the reference but not its delivery URL.  PLOS uses an
    ``info:doi`` identifier and eLife uses a TIFF filename served through its
    documented IIIF endpoint, so both need source-aware resolution.
    """

    graphic = figure.find(["graphic", "media"])
    if graphic is None:
        return None
    raw = graphic.get("xlink:href") or graphic.get("href")
    if not isinstance(raw, str) or not raw.strip() or not base_url:
        return None
    href = raw.strip()

    if source == "plos_jats" and href.casefold().startswith("info:doi/"):
        match = _PLOS_ARTICLE.search(base_url)
        if not match:
            return None
        identifier = href.removeprefix("info:doi/")
        encoded = quote(identifier, safe=".:/")
        return (
            f"https://journals.plos.org/{match.group(1)}/article/figure/image"
            f"?id={encoded}&size=inline"
        )

    if source == "elife_jats" and (match := _ELIFE_ARTICLE.search(base_url)):
        filename = href.rsplit("/", 1)[-1]
        if not filename or filename in {".", ".."}:
            return None
        encoded = quote(filename, safe="._-")
        return (
            f"https://iiif.elifesciences.org/lax:{match.group(1)}/{encoded}"
            "/full/,1000/0/default.jpg"
        )

    # Some JATS publishers put an absolute CDN URL directly in xlink:href.
    # Relative PMC asset paths need a publisher-specific resolver and are left
    # absent rather than turned into a plausible-looking broken API URL.
    if urlsplit(href).scheme in {"http", "https"}:
        return _http_url(href, base_url=base_url)
    return None
