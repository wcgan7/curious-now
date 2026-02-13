from __future__ import annotations

import re
from collections.abc import Callable
from io import BytesIO
from logging import Logger
from typing import Any
from urllib.parse import quote

import httpx

_FRONTMATTER_AFFILIATION_RE = re.compile(
    r"(?i)\b(department|university|institute|fellow|observatory|center|centre|school|laboratory)\b"
)
_ARXIV_HTML_FRONTMATTER_RE = re.compile(
    r"(?i)\b("
    r"department|university|institute|center|centre|observatory|school|laboratory|"
    r"correspondence|preprint|fellow|@"
    r")\b"
)


def _trim_html_frontmatter_to_abstract(text: str) -> str:
    lines = text.splitlines()
    abstract_idx = -1
    for i, ln in enumerate(lines[:260]):
        if ln.strip().lower() == "abstract":
            abstract_idx = i
            break
    if abstract_idx <= 2:
        return text

    prefix = lines[:abstract_idx]
    nonblank_prefix = [ln.strip() for ln in prefix if ln.strip()]
    if not nonblank_prefix:
        return text

    frontmatter_hits = 0
    for ln in nonblank_prefix:
        if _ARXIV_HTML_FRONTMATTER_RE.search(ln):
            frontmatter_hits += 1
            continue
        if re.match(r"^\[?\d+\]?\s", ln):
            frontmatter_hits += 1
            continue
    if frontmatter_hits < max(4, int(len(nonblank_prefix) * 0.35)):
        return text

    title_candidate = ""
    for ln in nonblank_prefix:
        t = ln.strip()
        if len(t.split()) < 4:
            continue
        if len(t) > 180:
            continue
        if _ARXIV_HTML_FRONTMATTER_RE.search(t):
            continue
        if re.match(r"^\[?\d+\]?\s", t):
            continue
        title_candidate = t
        break

    kept: list[str] = []
    if title_candidate:
        kept.extend([title_candidate, ""])
    kept.extend(lines[abstract_idx:])
    return "\n".join(kept).strip()


def _is_likely_heading(line: str) -> bool:
    t = line.strip()
    if not t:
        return False
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", t):
        return True
    if t.lower() in {"abstract", "introduction", "methods", "results", "discussion", "references"}:
        return True
    letter_count = sum(1 for ch in t if ch.isalpha())
    if (
        len(t) <= 80
        and letter_count >= 2
        and not re.search(r"\d", t)
        and t == t.title()
        and len(t.split()) <= 10
    ):
        return True
    return False


def _reflow_pdf_lines(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if re.match(r"^\d+$", line):
            # Standalone page numbers are common artifacts.
            continue
        if not out or out[-1] == "":
            # Merge across a single blank gap when a line-wrapped fragment was split by layout noise.
            if (
                out
                and out[-1] == ""
                and len(out) >= 2
                and out[-2]
                and not re.search(r"[.!?:)]$", out[-2])
                and re.match(r"^[a-z0-9(\[]", line)
                and not _is_likely_heading(out[-2])
                and not _is_likely_heading(line)
            ):
                out[-2] = f"{out[-2]} {line}"
                out.pop()
                continue
            out.append(line)
            continue

        prev = out[-1]
        if prev.endswith("-") and re.match(r"^[a-z]", line):
            prev_last_token = prev[:-1].split()[-1] if prev[:-1].split() else ""
            glue = "-" if "-" in prev_last_token else ""
            out[-1] = prev[:-1] + glue + line
            continue

        prev_ends_sentence = bool(re.search(r"[.!?:)]$", prev))
        cur_starts_cont = bool(re.match(r"^[a-z0-9(\[]", line))
        if (
            prev.lower().startswith("keywords:")
            and not _is_likely_heading(line)
            and len(line.split()) <= 8
            and not re.search(r"[.!?]", line)
        ):
            out[-1] = f"{prev} {line}"
            continue
        if prev.endswith(",") and not _is_likely_heading(line):
            out[-1] = f"{prev} {line}"
            continue
        if (
            not prev_ends_sentence
            and cur_starts_cont
            and not _is_likely_heading(prev)
            and not _is_likely_heading(line)
        ):
            out[-1] = f"{prev} {line}"
            continue
        out.append(line)

    return "\n".join(out)


def _looks_pdf_noise_line(line: str) -> bool:
    t = line.strip()
    if not t:
        return False
    if "|" in t:
        return False
    if re.match(r"^[a-z]\)$", t):
        return True
    if re.match(r"^Fig\.\s+[A-Za-z0-9]", t):
        return True
    if re.match(r"^Figure\s+[A-Za-z0-9]+:", t):
        return True
    if _is_likely_heading(t):
        return False
    if re.match(r"^[-−]?\d+(\.\d+)?(\s+[-−]?\d+(\.\d+)?){2,}$", t):
        return True
    if re.match(r"^[-−]?\d+\.\d+$", t):
        return True
    if re.match(r"^[A-Za-z]\]$", t):
        return True
    if re.match(r"^\d+(\.\d+)?\s+\d+(\.\d+)?\s+[a-zA-Z]\)", t):
        return True
    if t.lower().startswith(("arxiv:", "doi:")):
        return True
    has_math_marker = "\\" in t or "=" in t
    alpha = sum(1 for ch in t if ch.isalpha())
    digit = sum(1 for ch in t if ch.isdigit())
    if digit >= 5 and alpha > 0 and alpha / max(len(t), 1) < 0.22:
        return True
    # Figure/axis legends often become dense token soups with many numbers/symbols and
    # very little prose structure after PDF extraction.
    tokens = re.findall(r"\S+", t)
    if len(tokens) >= 8:
        short_tokens = sum(1 for tok in tokens if len(tok) <= 3)
        numeric_tokens = sum(1 for tok in tokens if re.search(r"\d", tok))
        alpha_tokens = [tok for tok in tokens if re.search(r"[A-Za-z]", tok)]
        stopword_tokens = sum(
            1
            for tok in alpha_tokens
            if tok.lower().strip(".,;:()[]{}") in {
                "the",
                "and",
                "for",
                "with",
                "from",
                "this",
                "that",
                "these",
                "those",
                "is",
                "are",
                "was",
                "were",
                "be",
                "in",
                "on",
                "of",
                "to",
                "by",
                "as",
                "we",
                "our",
                "their",
            }
        )
        stopword_ratio = stopword_tokens / max(1, len(alpha_tokens))
        short_ratio = short_tokens / max(1, len(tokens))
        has_plot_symbols = bool(re.search(r"[≈±χλμσΣΔ⊙\[\]{}]", t))
        has_panel_marker = bool(re.search(r"[a-zA-Z]\)", t))
        legend_like = (
            numeric_tokens >= 2
            and (short_ratio >= 0.30 or has_panel_marker)
            and stopword_ratio <= 0.25
            and has_plot_symbols
            and not t.endswith((".", "!", "?"))
        )
        panel_legend_like = (
            has_panel_marker
            and numeric_tokens >= 3
            and short_ratio >= 0.20
            and not t.endswith((".", "!", "?"))
        )
        if legend_like or panel_legend_like:
            return True

    # Standalone axis-label style rows (variable + units) are common visual artifacts.
    if re.match(r"^[A-Za-zα-ωΑ-Ω][A-Za-z0-9_α-ωΑ-Ω]*\s*\[[^\]]{1,24}\](\s*[A-Za-z0-9_/\-]+)?$", t):
        return True
    if has_math_marker:
        return False
    return False


def _filter_pdf_noise_lines(text: str) -> str:
    kept: list[str] = []
    for ln in text.splitlines():
        if _looks_pdf_noise_line(ln):
            continue
        kept.append(ln)
    return "\n".join(kept)


def _repair_pdf_broken_numeric_fragments(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""

        # Merge lines where a comparator expression is split across line break, e.g. "x <"
        # followed by "3 in ...".
        if re.search(r"[<>≤≥]\s*$", cur) and re.match(r"^\d", nxt):
            out.append(f"{cur} {nxt}")
            i += 1
            continue

        out.append(lines[i])
        i += 1

    return "\n".join(out)


def _trim_pdf_frontmatter(text: str) -> str:
    lines = text.splitlines()
    abstract_idx = -1
    for i, ln in enumerate(lines[:260]):
        if ln.strip().lower() == "abstract":
            abstract_idx = i
            break
    if abstract_idx <= 0:
        return text

    title_candidate = ""
    for ln in lines[:abstract_idx]:
        t = ln.strip()
        if not t:
            continue
        if len(t.split()) < 4:
            continue
        if _FRONTMATTER_AFFILIATION_RE.search(t):
            continue
        if re.search(r"[@]|arxiv:", t, flags=re.IGNORECASE):
            continue
        if re.match(r"^[\[\(]?\d+[\]\)]?\s", t):
            continue
        title_candidate = t
        break

    kept = lines[abstract_idx:]
    if title_candidate and kept:
        first_chunk = "\n".join(kept[:12])
        if title_candidate not in first_chunk:
            return f"{title_candidate}\n\n" + "\n".join(kept)
    return "\n".join(kept)


def _postprocess_pdf_text(text: str) -> str:
    reflowed = _reflow_pdf_lines(text)
    repaired = _repair_pdf_broken_numeric_fragments(reflowed)
    filtered = _filter_pdf_noise_lines(repaired)
    trimmed = _trim_pdf_frontmatter(filtered)
    # Tidy line spacing introduced by joins and trimming.
    trimmed = re.sub(r"\n{3,}", "\n\n", trimmed).strip()
    return trimmed


def _page_text_from_blocks(blocks: list[Any], *, page_width: float) -> str:
    parsed: list[tuple[float, float, float, float, str]] = []
    for block in blocks:
        if not isinstance(block, (list, tuple)) or len(block) < 5:
            continue
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        if not isinstance(text, str):
            continue
        compact = text.strip()
        if not compact:
            continue
        parsed.append((float(x0), float(y0), float(x1), float(y1), compact))
    if not parsed:
        return ""

    def _sort_yx(items: list[tuple[float, float, float, float, str]]) -> list[tuple[float, float, float, float, str]]:
        return sorted(items, key=lambda b: (b[1], b[0]))

    # Default read order for most pages.
    fallback_lines = [b[4] for b in _sort_yx(parsed)]
    if len(parsed) < 6 or page_width <= 0:
        return "\n".join(fallback_lines)

    mid = page_width / 2.0
    left = [b for b in parsed if ((b[0] + b[2]) / 2.0) <= mid]
    right = [b for b in parsed if ((b[0] + b[2]) / 2.0) > mid]
    if min(len(left), len(right)) < 3:
        return "\n".join(fallback_lines)

    left_max_x = max(b[2] for b in left)
    right_min_x = min(b[0] for b in right)
    gap = right_min_x - left_max_x
    if gap < page_width * 0.03:
        return "\n".join(fallback_lines)

    if max(len(left), len(right)) / max(1, min(len(left), len(right))) > 5.0:
        return "\n".join(fallback_lines)

    left_lines = [b[4] for b in _sort_yx(left)]
    right_lines = [b[4] for b in _sort_yx(right)]
    return "\n".join(left_lines + [""] + right_lines)


def _serialize_pdf_table_rows(rows: list[list[str | None]]) -> str | None:
    def _normalize_cell(value: str | None) -> str:
        text = re.sub(r"\s+", " ", (value or "").strip())
        # Fix line-wrap hyphenation inside a table cell, e.g. "imple- mentation".
        text = re.sub(r"\b([A-Za-z]{2,})-\s+([a-z]{2,})\b", r"\1\2", text)
        return text

    normalized_rows: list[list[str]] = []
    for row in rows:
        cells = [_normalize_cell(c) for c in row]
        if any(cells):
            normalized_rows.append(cells)
    if len(normalized_rows) < 2:
        return None
    max_cols = max(len(r) for r in normalized_rows)
    if max_cols < 2:
        return None
    non_empty = sum(1 for r in normalized_rows for c in r if c)
    total = max_cols * len(normalized_rows)
    if total <= 0 or (non_empty / total) < 0.30:
        return None

    alpha_cells = 0
    split_like_cells = 0
    for normalized_row in normalized_rows[1:] if len(normalized_rows) > 1 else normalized_rows:
        for cell in normalized_row:
            if not cell:
                continue
            if re.fullmatch(r"[A-Za-z]{2,12}", cell):
                alpha_cells += 1
                lower = cell.lower()
                if lower in {
                    "the",
                    "and",
                    "for",
                    "with",
                    "from",
                    "into",
                    "edge",
                    "score",
                    "round",
                    "query",
                    "key",
                    "agent",
                    "outcome",
                }:
                    continue
                if cell[0].islower():
                    split_like_cells += 1
    split_rate = split_like_cells / max(1, alpha_cells)
    avg_non_empty_per_row = non_empty / max(1, len(normalized_rows))
    if max_cols >= 5 and avg_non_empty_per_row >= 4.0 and split_rate >= 0.45:
        return None

    aligned = [r + [""] * (max_cols - len(r)) for r in normalized_rows]
    header = aligned[0]
    body = aligned[1:]
    lines = [" | ".join(header), " | ".join(["---"] * max_cols)]
    lines.extend(" | ".join(r) for r in body)
    return "\n".join(lines)


def _extract_pdf_tables(pdf_bytes: bytes, *, logger: Logger) -> list[str]:
    try:
        import pdfplumber
    except Exception:
        return []
    table_settings_variants = [
        None,
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
        {"vertical_strategy": "lines", "horizontal_strategy": "text"},
        {"vertical_strategy": "text", "horizontal_strategy": "lines"},
    ]
    max_tables = 8
    max_table_chars = 16_000
    tables_out: list[str] = []
    seen_blocks: list[str] = []

    def _is_near_duplicate_table(key: str) -> bool:
        for existing in seen_blocks:
            if key == existing:
                return True
            if key in existing or existing in key:
                return True
            a = set(key.split())
            b = set(existing.split())
            if not a or not b:
                continue
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if overlap >= 0.92:
                return True
        return False
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                table_idx = 0
                for settings in table_settings_variants:
                    try:
                        tables = page.extract_tables(table_settings=settings) if settings else page.extract_tables()
                    except Exception:
                        tables = []
                    for table in tables:
                        if not table:
                            continue
                        serialized = _serialize_pdf_table_rows(table)
                        if not serialized:
                            continue
                        dedupe_key = re.sub(r"\s+", " ", serialized).strip().lower()
                        if _is_near_duplicate_table(dedupe_key):
                            continue
                        seen_blocks.append(dedupe_key)
                        table_idx += 1
                        block = f"Table (PDF p.{page_idx}.{table_idx})\n{serialized}"
                        tables_out.append(block)
                        if len(tables_out) >= max_tables:
                            return tables_out
                        if sum(len(x) for x in tables_out) >= max_table_chars:
                            return tables_out
    except Exception as exc:
        logger.debug("pdfplumber table extraction failed: %s", exc)
        return []
    return tables_out


def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    clean_full_text: Callable[[str | None], str | None],
    logger: Logger,
) -> str | None:
    try:
        import fitz
    except Exception:
        logger.warning("PyMuPDF unavailable; cannot parse PDF full text")
        return None

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return None

    pages: list[str] = []
    try:
        for page in doc:
            page_text = ""
            try:
                blocks = page.get_text("blocks")
            except Exception:
                blocks = []
            if blocks:
                page_text = _page_text_from_blocks(blocks, page_width=float(page.rect.width))
            if not page_text:
                page_text = page.get_text("text")
            if page_text and page_text.strip():
                pages.append(page_text)
    finally:
        doc.close()

    if not pages:
        return None
    raw_text = "\n\n".join(pages)
    table_blocks = _extract_pdf_tables(pdf_bytes, logger=logger)
    if table_blocks:
        raw_text = raw_text + "\n\n" + "\n\n".join(table_blocks)
    processed = _postprocess_pdf_text(raw_text)
    return clean_full_text(processed)


def fetch_pdf_text(
    url: str,
    *,
    http_get: Callable[[str], httpx.Response],
    extract_pdf_text_fn: Callable[[bytes], str | None],
    is_fulltext_quality_sufficient: Callable[[str | None], bool],
    on_quality_rejected: Callable[[str], None] | None = None,
) -> str | None:
    resp = http_get(url)
    if resp.status_code != 200:
        return None

    content_type = (resp.headers.get("content-type") or "").lower()
    content = resp.content
    if not content:
        return None
    if "pdf" not in content_type and not content.startswith(b"%PDF"):
        return None

    text = extract_pdf_text_fn(content)
    if not text:
        return None
    if not is_fulltext_quality_sufficient(text):
        if on_quality_rejected is not None:
            on_quality_rejected(text)
        return None
    return text


def extract_html_body_text(
    raw_html: str,
    *,
    clean_full_text: Callable[[str | None], str | None],
) -> str | None:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
            tag.decompose()
        for selector in (
            "nav",
            "header",
            "footer",
            "aside",
            ".ltx_page_footer",
            ".ltx_page_header",
        ):
            for node in soup.select(selector):
                node.decompose()
        for img in soup.find_all("img"):
            img.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "\n", text)
    return clean_full_text(text)


def extract_arxiv_html_body_text(
    raw_html: str,
    *,
    clean_full_text: Callable[[str | None], str | None],
    compact_spaces: Callable[[str], str],
) -> str | None:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "template"]):
            tag.decompose()
        for selector in (
            "nav",
            "header",
            "footer",
            "aside",
            "button",
            ".sr-only",
            ".ltx_keywords",
            ".ltx_page_footer",
            ".ltx_page_header",
            ".ltx_note_mark",
            ".ltx_ERROR",
        ):
            for node in soup.select(selector):
                node.decompose()

        for m in soup.find_all("math"):
            tex = None
            ann = m.find("annotation", attrs={"encoding": "application/x-tex"})
            if ann is not None:
                candidate = ann.get_text(" ", strip=True)
                if candidate:
                    tex = candidate
            if not tex:
                alt = m.get("alttext") or m.get("aria-label")
                if isinstance(alt, str) and alt.strip():
                    tex = alt.strip()
            replacement = f" {tex} " if tex else " [MATH] "
            m.replace_with(soup.new_string(replacement))

        def _cell_text(cell: Any) -> str:
            return compact_spaces(cell.get_text(" ", strip=True))

        def _serialize_table(table_node: Any, caption_text: str | None = None) -> str:
            rows = table_node.find_all("tr")
            parsed_rows: list[list[str]] = []
            for tr in rows:
                cells = tr.find_all(["th", "td"])
                if not cells:
                    continue
                row = [_cell_text(c) for c in cells]
                if any(x for x in row):
                    parsed_rows.append(row)
            if not parsed_rows:
                return compact_spaces(caption_text or "")

            max_cols = max(len(r) for r in parsed_rows)
            normalized_rows = [r + [""] * (max_cols - len(r)) for r in parsed_rows]
            header = normalized_rows[0]
            body_rows = normalized_rows[1:] if len(normalized_rows) > 1 else []

            lines: list[str] = []
            if caption_text:
                lines.append(caption_text)
            lines.append(" | ".join(header))
            if body_rows:
                lines.append(" | ".join(["---"] * max_cols))
                lines.extend(" | ".join(r) for r in body_rows)
            return "\n".join(lines)

        for fig in soup.select("figure.ltx_table"):
            caption = fig.find("figcaption")
            caption_text = compact_spaces(caption.get_text(" ", strip=True)) if caption else None
            table = fig.find("table")
            if table is None:
                if caption_text:
                    p = soup.new_tag("p")
                    p.string = caption_text
                    fig.replace_with(p)
                else:
                    fig.decompose()
                continue
            serialized = _serialize_table(table, caption_text)
            pre = soup.new_tag("pre")
            pre["data-cn-table"] = "1"
            pre.string = serialized
            fig.replace_with(pre)

        for table in soup.select("table.ltx_tabular"):
            if table.find_parent("figure", class_="ltx_table"):
                continue
            serialized = _serialize_table(table, None)
            pre = soup.new_tag("pre")
            pre["data-cn-table"] = "1"
            pre.string = serialized
            table.replace_with(pre)

        root = soup.find("main") or soup.find("article") or soup.body or soup
        block_tags = {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "li",
            "dt",
            "dd",
            "figcaption",
            "blockquote",
            "pre",
        }
        blocks: list[str] = []
        seen_blocks: set[str] = set()
        for node in root.find_all(block_tags):
            if node.find_parent(["script", "style"]):
                continue
            if node.name == "pre" and node.get("data-cn-table") == "1":
                raw = node.get_text("\n", strip=True)
                lines = [compact_spaces(ln) for ln in raw.splitlines() if compact_spaces(ln)]
                text = "\n".join(lines)
            else:
                text = compact_spaces(node.get_text(" ", strip=True))
            if len(text) < 2:
                continue
            key = text.lower()
            if len(key) >= 30 and key in seen_blocks:
                continue
            seen_blocks.add(key)
            blocks.append(text)

        for text_node in root.find_all(string=True):
            parent = getattr(text_node, "parent", None)
            parent_name = getattr(parent, "name", "")
            if parent_name in block_tags or parent_name in {"script", "style"}:
                continue
            if parent and parent.find_parent(["figure", "table", "math"]):
                continue
            if parent_name not in {"main", "article", "section", "div"}:
                continue
            text = compact_spaces(str(text_node))
            if len(text) < 20:
                continue
            blocks.append(text)

        if blocks:
            text = "\n\n".join(blocks)
        else:
            text = root.get_text("\n")
    except Exception:
        return extract_html_body_text(raw_html, clean_full_text=clean_full_text)
    text = _trim_html_frontmatter_to_abstract(text)
    return clean_full_text(text)


def fetch_arxiv_pdf_full_text(
    arxiv_id: str,
    *,
    fetch_pdf_text_fn: Callable[[str], str | None],
) -> str | None:
    pdf_url = f"https://arxiv.org/pdf/{quote(arxiv_id)}.pdf"
    return fetch_pdf_text_fn(pdf_url)


def fetch_arxiv_html_full_text(
    arxiv_id: str,
    *,
    http_get: Callable[[str], httpx.Response],
    extract_arxiv_html_body_text_fn: Callable[[str], str | None],
    is_fulltext_quality_sufficient: Callable[[str | None], bool],
) -> str | None:
    html_url = f"https://arxiv.org/html/{quote(arxiv_id)}"
    resp = http_get(html_url)
    if resp.status_code != 200:
        return None
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return None
    text = extract_arxiv_html_body_text_fn(resp.text)
    if not text or not is_fulltext_quality_sufficient(text):
        return None
    return text
