from __future__ import annotations

import hashlib
import html
import io
import logging
import re
import tarfile
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row

from curious_now.extractors import paper_sources as extractors
from curious_now.settings import get_settings

logger = logging.getLogger(__name__)

_PAPER_CONTENT_TYPES = ("preprint", "peer_reviewed")
_MAX_FULL_TEXT_CHARS = 120_000
_MIN_FULLTEXT_CHARS = 2_500
_MIN_FULLTEXT_WORDS = 400

_KIND_ABSTRACT = "abstract"
_KIND_FULLTEXT = "fulltext"
_SOURCE_QUALITY_BONUS: dict[str, float] = {
    "arxiv_html": 0.18,
    "arxiv_pdf": 0.12,
    "arxiv_eprint": 0.08,
}
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_YEAR_RE = re.compile(r"^(19|20)\d{2}[a-z]?$")
_MATH_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9_{}^\\()+\-*=.,|∣∈Σ⊕→≤≥⋅×τσℋℳ𝒩𝒜𝒟\[\]\s]+$"
)


@dataclass(frozen=True)
class HydratePaperTextResult:
    items_scanned: int
    items_hydrated: int
    items_failed: int
    items_skipped: int


@dataclass(frozen=True)
class OACandidate:
    url: str
    source: str
    is_pdf: bool
    open_access_ok: bool
    license_name: str | None


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value).replace("\x00", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:_MAX_FULL_TEXT_CHARS]


def _compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _drop_early_duplicate_lines(lines: list[str], *, max_scan: int = 120) -> list[str]:
    scan_limit = max_scan
    if max_scan == 120:
        scan_limit = min(max(60, len(lines) // 5), 240)
    seen: set[str] = set()
    out: list[str] = []
    for idx, line in enumerate(lines):
        raw = line.strip()
        key = line.strip().lower()
        words = len(key.split())
        header_like = 2 <= words <= 14 and not key.endswith((".", "!", "?"))
        has_upper = bool(re.search(r"[A-Z]", raw))
        if (
            idx < scan_limit
            and key
            and len(key) >= 6
            and header_like
            and has_upper
            and not any(ch in key for ch in "()[]{}\\")
            and not re.search(r"\b(19|20)\d{2}\b", key)
            and key in seen
        ):
            continue
        if key:
            seen.add(key)
        out.append(line)
    return out


def _is_citation_like_token(token: str) -> bool:
    t = token.strip()
    if not t:
        return False
    if t in {"(", ")", ",", ";", ":", ".", "et al.", "et al"}:
        return True
    if _YEAR_RE.match(t):
        return True
    if re.match(r"^[A-Za-z][A-Za-z\-' ]{0,40}$", t):
        return True
    if re.match(r"^\d{1,4}([,-]\d{1,4})*$", t):
        return True
    return False


def _is_citation_like_chunk(chunk: str) -> bool:
    c = chunk.strip()
    if not c:
        return False
    if len(c) > 140 or re.search(r"[!?]", c):
        return False
    parts = [p for p in re.split(r"[;,:()\s]+", c) if p]
    if not parts:
        return False
    for part in parts:
        p = part.strip().strip(".")
        if not p:
            continue
        if _YEAR_RE.match(p):
            continue
        if p.lower() in {"et", "al"}:
            continue
        if re.match(r"^\d{1,4}([,-]\d{1,4})*$", p):
            continue
        if re.match(r"^[A-Za-z][A-Za-z\-'’]{0,40}$", p):
            continue
        return False
    return True


def _normalize_citation_body(text: str) -> str:
    body = _compact_spaces(text)
    if not body:
        return body
    body = body.replace("et al ,", "et al,")
    body = re.sub(r"\bet\s+al\s*\.\s*\.", "et al.", body, flags=re.IGNORECASE)
    body = re.sub(r"\bet\s+al\s*\.", "et al.", body, flags=re.IGNORECASE)
    body = re.sub(r"\bet\s+al\b", "et al.", body, flags=re.IGNORECASE)
    body = body.replace("et al..", "et al.")
    body = re.sub(r"\s+([,;:)\]])", r"\1", body)
    body = re.sub(r"([(\[])\s+", r"\1", body)
    body = re.sub(r"([,;:])(?=\S)", r"\1 ", body)
    body = re.sub(r"\s{2,}", " ", body).strip(" ;,")
    return body


def _stitch_citation_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == "(":
            open_char = "("
            close_char = ")"
        elif line == "[":
            open_char = "["
            close_char = "]"
        elif line.startswith("(") and ")" not in line:
            open_char = "("
            close_char = ")"
        elif line.startswith("[") and "]" not in line:
            open_char = "["
            close_char = "]"
        else:
            out.append(lines[i])
            i += 1
            continue

        chunks: list[str] = []
        if line not in {"(", "["}:
            chunks.append(line[1:].strip())
        j = i + 1
        close_at = None
        close_tail = ""
        while j < len(lines) and (j - i) <= 30:
            t = lines[j].strip()
            if not t:
                j += 1
                continue
            if close_char in t:
                before_close, _sep, tail = t.partition(close_char)
                chunks.append(before_close.strip())
                close_at = j
                close_tail = tail.strip()
                break
            chunks.append(t)
            t_clean = t.rstrip(".,;:()[]")
            token_for_check = t if t in {"(", ")", "[", "]", ",", ";", ":", "."} else t_clean
            if not _is_citation_like_token(token_for_check) and not _is_citation_like_chunk(t):
                break
            j += 1

        if close_at is None:
            out.append(lines[i])
            i += 1
            continue

        body = _normalize_citation_body(" ".join(chunks))
        year_count = len(re.findall(r"\b(19|20)\d{2}[a-z]?\b", body))
        alpha_seen = bool(re.search(r"[A-Za-z]", body))
        token_count = len(body.split())
        numeric_only = bool(re.fullmatch(r"[\d,\-\s]+", body))
        is_author_year = year_count >= 1 and alpha_seen
        is_numeric_bracket = open_char == "[" and numeric_only and token_count <= 30
        if (is_author_year or is_numeric_bracket) and 1 <= token_count <= 60:
            out.append(f"{open_char}{body}{close_char}")
            if close_tail:
                out.append(close_tail)
            i = close_at + 1
            continue

        out.append(lines[i])
        i += 1
    return out


def _looks_math_fragment(line: str) -> bool:
    compact = line.strip()
    if not compact:
        return False
    if compact.count("|") >= 2:
        return False
    if compact.startswith("--- |") or compact.startswith("| ---"):
        return False
    word_count = len(compact.split())
    if word_count > 8 and not compact.startswith("\\"):
        return False
    if compact in {"(", ")", ",", ".", ":", ";", "+", "-", "=", "{", "}"}:
        return True
    if _YEAR_RE.match(compact):
        return False
    if re.match(r"^\(\d+\)$", compact):
        return True
    if re.match(r"^[A-Za-z]$", compact):
        return True
    if re.match(r"^\d{1,3}$", compact):
        return True
    if re.search(r"[\\^_=+\-*/{}\[\]|<>∣∈Σ⊕→≤≥⋅×]", compact):
        return True
    if re.search(r"[0-9]", compact) and re.search(r"[A-Za-z]", compact):
        return True
    if not _MATH_TOKEN_RE.match(compact):
        return False
    if re.match(r"^[A-Za-z]{3,}$", compact):
        return False
    return len(compact) <= 40


def _join_math_tokens(tokens: list[str]) -> str:
    merged = ""
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        if t in {")", "]", "}", ",", ";", ":"}:
            merged = merged.rstrip() + t
            continue
        if t in {"(", "[", "{"}:
            if merged and not merged.endswith(" "):
                merged += " "
            merged += t
            continue
        if merged and re.search(r"[A-Za-z0-9]$", merged) and re.match(r"^[A-Za-z0-9]", t):
            merged += " "
        merged += t
    merged = re.sub(r"\s+", " ", merged).strip()
    return merged


def _stitch_math_spill_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not _looks_math_fragment(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        j = i
        tokens: list[str] = []
        while j < len(lines) and _looks_math_fragment(lines[j]):
            tokens.append(lines[j])
            j += 1
        if len(tokens) >= 6:
            merged = _join_math_tokens(tokens)
            out.append(merged if merged else lines[i])
        else:
            out.extend(tokens)
        i = j
    return out


def _dedupe_adjacent_latex_unicode(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        cur = line.strip()
        if not out:
            out.append(line)
            continue
        prev = out[-1].strip()
        if not cur or not prev:
            out.append(line)
            continue
        prev_norm = re.sub(r"[^A-Za-z0-9]+", "", prev).lower()
        cur_norm = re.sub(r"[^A-Za-z0-9]+", "", cur.replace("\\", "")).lower()
        if "\\" in cur and prev_norm and prev_norm == cur_norm:
            continue
        out.append(line)
    return out


def _reflow_inline_fragments(lines: list[str]) -> list[str]:
    connector_words = {
        "and",
        "or",
        "to",
        "of",
        "in",
        "for",
        "with",
        "via",
        "by",
        "from",
        "as",
        "on",
        "at",
        "where",
        "which",
        "that",
        "while",
        "when",
        "whose",
    }
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        line_words = line.split()
        starts_like_continuation = bool(line and (line[0].islower() or line[0] in {",", ";", ":"}))
        first_word = line_words[0].lower() if line_words else ""
        if (
            out
            and line
            and len(line_words) <= 3
            and i + 1 < len(lines)
            and len(out[-1].split()) >= 10
            and len(lines[i + 1].strip().split()) >= 6
            and not re.match(r"^\d+(\.\d+)*$", line)
            and not re.match(r"^[A-Z][A-Za-z0-9\- ]{2,50}$", line)
            and (starts_like_continuation or first_word in connector_words)
            and not out[-1].strip().endswith((".", "!", "?"))
        ):
            out[-1] = _compact_spaces(out[-1] + " " + line)
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def _merge_section_number_headings(lines: list[str]) -> list[str]:
    def _looks_heading_title(text: str) -> bool:
        t = text.strip()
        if not t or len(t) > 120:
            return False
        if t.lower() in {"figure", "table", "fig.", "tab."}:
            return False
        if t.endswith((".", "!", "?")):
            return False
        words = t.split()
        if len(words) > 12:
            return False
        letter_count = sum(1 for ch in t if unicodedata.category(ch).startswith("L"))
        if letter_count < 2:
            return False
        return True

    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        nxt2 = lines[i + 2].strip() if i + 2 < len(lines) else ""
        if (
            re.match(r"^\d+(\.\d+)*$", cur)
            and nxt
            and _looks_heading_title(nxt)
        ):
            out.append(f"{cur} {nxt}")
            i += 2
            continue
        if (
            re.match(r"^\d+(\.\d+)*$", cur)
            and not nxt
            and nxt2
            and _looks_heading_title(nxt2)
        ):
            out.append(f"{cur} {nxt2}")
            i += 3
            continue
        out.append(lines[i])
        i += 1
    return out


def _merge_leading_punctuation_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        cur = line.strip()
        if out and cur and cur[0] in {",", ";", ":", ".", ")"}:
            out[-1] = _compact_spaces(out[-1].rstrip() + cur)
            continue
        out.append(line)
    return out


def _dedupe_adjacent_semantic_repeats(lines: list[str]) -> list[str]:
    out: list[str] = []

    def _normalize_for_compare(text: str) -> str:
        t = re.sub(r"^[•*·-]\s+", "", text.strip())
        t = re.sub(r"\s+", " ", t)
        t = t.strip(" .;:,")
        return t.lower()

    for line in lines:
        cur = line.strip()
        if not out:
            out.append(line)
            continue
        if not cur:
            out.append(line)
            continue

        prev_idx = -1
        for idx in range(len(out) - 1, -1, -1):
            if out[idx].strip():
                prev_idx = idx
                break
        if prev_idx < 0:
            out.append(line)
            continue

        prev = out[prev_idx].strip()
        prev_norm = _normalize_for_compare(prev)
        cur_norm = _normalize_for_compare(cur)
        blank_gap = sum(1 for x in out[prev_idx + 1 :] if not x.strip())
        if prev_norm and prev_norm == cur_norm and len(cur_norm) >= 20 and blank_gap <= 1:
            continue
        out.append(line)
    return out


def _drop_visual_legend_artifacts(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        t = line.strip()
        if not t:
            out.append(line)
            continue
        if re.match(r"^\d+(\.\d+)?\s+\d+(\.\d+)?$", t):
            continue
        if re.match(r"^[a-zA-Z]\)$", t):
            continue
        if re.match(r"^[-−]?\d+\.\d+$", t):
            continue
        if re.match(r"^[A-Za-z]\]$", t):
            continue
        tokens = re.findall(r"\S+", t)
        if len(tokens) >= 8:
            short_tokens = sum(1 for tok in tokens if len(tok) <= 3)
            numeric_tokens = sum(1 for tok in tokens if re.search(r"\d", tok))
            has_panel_marker = bool(re.search(r"[a-zA-Z]\)", t))
            has_plot_symbols = bool(re.search(r"[≈±χλμσΣΔ⊙\[\]{}]", t))
            short_ratio = short_tokens / max(1, len(tokens))
            if (
                numeric_tokens >= 3
                and (has_panel_marker or has_plot_symbols)
                and short_ratio >= 0.20
                and not t.endswith((".", "!", "?"))
            ):
                continue
        if re.match(r"^[A-Za-zα-ωΑ-Ω][A-Za-z0-9_α-ωΑ-Ω]*\s*\[[^\]]{1,24}\](\s*[A-Za-z0-9_/\-]+)?$", t):
            continue
        out.append(line)
    return out


def _normalize_inline_tex_tokens(text: str) -> str:
    out = text
    replacements = {
        r"\\rightarrow": "→",
        r"\\to": "→",
        r"\\leftarrow": "←",
        r"\\leftrightarrow": "↔",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\in": "∈",
        r"\\notin": "∉",
        r"\\pm": "±",
    }
    for src, dst in replacements.items():
        out = re.sub(src + r"\b", dst, out)
    # Tidy spacing around common math operators after TeX normalization.
    out = re.sub(r"\s*([→←↔≤≥×±·∈∉])\s*", r"\1", out)
    # Tidy generic prose punctuation spacing.
    out = re.sub(r"\s+([,;:.!?])", r"\1", out)
    out = re.sub(r"([(\[])\s+", r"\1", out)
    out = re.sub(r"\s+([)\]])", r"\1", out)
    out = re.sub(r"([,;:])(?=\S)", r"\1 ", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out


def _normalize_extracted_lines(lines: list[str]) -> list[str]:
    processed = [unicodedata.normalize("NFKC", _ZERO_WIDTH_RE.sub("", ln)) for ln in lines]
    processed = _drop_early_duplicate_lines(processed)
    processed = _stitch_citation_lines(processed)
    processed = _stitch_math_spill_lines(processed)
    processed = _dedupe_adjacent_latex_unicode(processed)
    processed = _reflow_inline_fragments(processed)
    processed = _merge_section_number_headings(processed)
    processed = _merge_leading_punctuation_lines(processed)
    processed = _dedupe_adjacent_semantic_repeats(processed)
    processed = _drop_visual_legend_artifacts(processed)

    normalized: list[str] = []
    blank_run = 0
    for line in processed:
        compact = re.sub(r"[ \t]+", " ", line).strip()
        if not compact:
            blank_run += 1
            if blank_run <= 1:
                normalized.append("")
            continue
        blank_run = 0
        compact = _normalize_inline_tex_tokens(compact)
        normalized.append(compact)
    return normalized


def _clean_full_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value).replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"\u00a0", " ", text)
    looks_like_html = bool(
        re.search(r"<\s*(html|body|main|article|div|p|span|h[1-6]|table|tr|td|th|script|style)\b", text, re.IGNORECASE)
        or re.search(r"</\s*[a-zA-Z][^>]*>", text)
    )
    if looks_like_html:
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "\n", text)

    normalized_lines = _normalize_extracted_lines(text.split("\n"))

    out = "\n".join(normalized_lines).strip()
    if not out:
        return None
    return out[:_MAX_FULL_TEXT_CHARS]


def _is_fulltext_quality_sufficient(text: str | None) -> bool:
    if not text:
        return False
    if _score_fulltext_quality(text) < 0.4:
        return False
    words = len(text.split())
    chars = len(text)
    if chars < _MIN_FULLTEXT_CHARS or words < _MIN_FULLTEXT_WORDS:
        return False
    lower = text.lower()
    section_hits = sum(
        1
        for token in (
            "introduction",
            "method",
            "results",
            "discussion",
            "conclusion",
            "references",
        )
        if token in lower
    )
    return section_hits >= 2


def _score_fulltext_quality(text: str | None) -> float:
    if not text:
        return 0.0
    words = len(text.split())
    chars = len(text)
    lower = text.lower()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    line_count = len(lines)
    section_hits = sum(
        1
        for token in (
            "introduction",
            "background",
            "method",
            "methods",
            "results",
            "discussion",
            "conclusion",
            "references",
        )
        if token in lower
    )
    caption_hits = sum(lower.count(token) for token in ("figure", "fig.", "table"))
    short_noise_lines = sum(1 for ln in lines if len(ln) <= 2)
    long_glued_tokens = len(re.findall(r"\b[A-Za-z]{20,}\b", text))
    control_chars = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\t\r")
    pipe_table_lines = sum(1 for ln in lines if ln.count("|") >= 2)
    table_marker_hits = text.count("Table (PDF p.")

    abstract_idx = -1
    for idx, ln in enumerate(lines[:260]):
        if ln.lower() == "abstract":
            abstract_idx = idx
            break
    pre_abstract_affiliation_hits = 0
    if abstract_idx > 10:
        pre_lines = lines[:abstract_idx]
        for ln in pre_lines:
            if re.search(r"\b(department|university|institute|center|centre|observatory|fellow|preprint)\b", ln, re.IGNORECASE):
                pre_abstract_affiliation_hits += 1
            elif "@" in ln:
                pre_abstract_affiliation_hits += 1
            elif re.match(r"^\[?\d+\]?\s", ln):
                pre_abstract_affiliation_hits += 1

    score = 0.0
    score += min(chars / 18_000.0, 1.0) * 0.35
    score += min(words / 2_200.0, 1.0) * 0.35
    score += min(section_hits / 5.0, 1.0) * 0.30
    score -= min(caption_hits / 120.0, 0.20)
    score -= min((short_noise_lines / max(1, line_count)) * 1.8, 0.22)
    score -= min((long_glued_tokens / max(1, words)) * 8.0, 0.22)
    score -= min(control_chars / 40.0, 0.18)
    score -= min((pipe_table_lines / max(1, line_count)) * 1.5, 0.15)
    score -= min(table_marker_hits / 20.0, 0.10)
    if pre_abstract_affiliation_hits >= 4:
        score -= 0.12
    return max(0.0, min(1.0, score))


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


def _extract_pdf_text(pdf_bytes: bytes) -> str | None:
    return extractors.extract_pdf_text(
        pdf_bytes,
        clean_full_text=_clean_full_text,
        logger=logger,
    )


def _dump_rejected_pdf_text_for_debug(url: str, text: str) -> None:
    try:
        settings = get_settings()
    except Exception:
        return
    if not settings.paper_text_debug_dump_pdf_rejected:
        return
    dump_dir = settings.paper_text_debug_dump_dir
    if not dump_dir:
        return
    try:
        score = _score_fulltext_quality(text)
        digest = hashlib.sha1(f"{url}|{len(text)}|{score:.4f}".encode()).hexdigest()[:12]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = Path(dump_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"pdf-rejected-{ts}-{digest}.txt"
        payload = (
            f"url: {url}\n"
            f"reason: quality_rejected\n"
            f"score: {score:.4f}\n"
            f"chars: {len(text)}\n"
            f"words: {len(text.split())}\n\n"
            f"{text}"
        )
        path.write_text(payload, encoding="utf-8")
        logger.info("wrote rejected PDF debug dump to %s", path)
    except Exception as exc:
        logger.warning("failed to write rejected PDF debug dump: %s", exc)


def _fetch_pdf_text(url: str) -> str | None:
    return extractors.fetch_pdf_text(
        url,
        http_get=lambda u: _http_get(u, timeout_s=20.0),
        extract_pdf_text_fn=_extract_pdf_text,
        is_fulltext_quality_sufficient=_is_fulltext_quality_sufficient,
        on_quality_rejected=lambda t: _dump_rejected_pdf_text_for_debug(url, t),
    )


def _latex_to_text(tex: str) -> str | None:
    try:
        from pylatexenc.latex2text import LatexNodes2Text

        converter = LatexNodes2Text(math_mode="with-delimiters")
        converted = converter.latex_to_text(tex)
        return str(converted)
    except Exception:
        cleaned = re.sub(r"(?m)(?<!\\)%.*$", "", tex)
        cleaned = re.sub(
            r"\\begin\{equation\*?\}[\\s\\S]*?\\end\{equation\*?\}",
            "\n[MATH]\n",
            cleaned,
        )
        cleaned = re.sub(r"\\begin\{align\*?\}[\\s\\S]*?\\end\{align\*?\}", "\n[MATH]\n", cleaned)
        cleaned = re.sub(
            r"\\begin\{figure\*?\}[\\s\\S]*?\\end\{figure\*?\}",
            "\n[FIGURE]\n",
            cleaned,
        )
        cleaned = re.sub(r"\\begin\{table\*?\}[\\s\\S]*?\\end\{table\*?\}", "\n[TABLE]\n", cleaned)
        cleaned = re.sub(r"\$[^$]+\$", " [MATH] ", cleaned)
        cleaned = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", cleaned)
        cleaned = cleaned.replace("{", " ").replace("}", " ")
        return cleaned


def _extract_html_body_text(raw_html: str) -> str | None:
    return extractors.extract_html_body_text(
        raw_html,
        clean_full_text=_clean_full_text,
    )


def _extract_arxiv_html_body_text(raw_html: str) -> str | None:
    return extractors.extract_arxiv_html_body_text(
        raw_html,
        clean_full_text=_clean_full_text,
        compact_spaces=_compact_spaces,
    )


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


def _fetch_arxiv_pdf_full_text(arxiv_id: str) -> str | None:
    return extractors.fetch_arxiv_pdf_full_text(
        arxiv_id,
        fetch_pdf_text_fn=_fetch_pdf_text,
    )


def _fetch_arxiv_html_full_text(arxiv_id: str) -> str | None:
    return extractors.fetch_arxiv_html_full_text(
        arxiv_id,
        http_get=lambda u: _http_get(u, timeout_s=20.0),
        extract_arxiv_html_body_text_fn=_extract_arxiv_html_body_text,
        is_fulltext_quality_sufficient=_is_fulltext_quality_sufficient,
    )


def _fetch_arxiv_html_image_url(arxiv_id: str) -> str | None:
    html_url = f"https://arxiv.org/html/{quote(arxiv_id)}"
    resp = _http_get(html_url, timeout_s=20.0)
    if resp.status_code != 200:
        return None
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return None
    return extractors.extract_arxiv_html_image_url(resp.text, base_url=html_url)


def _fetch_arxiv_eprint_full_text(arxiv_id: str) -> str | None:
    url = f"https://arxiv.org/e-print/{quote(arxiv_id)}"
    resp = _http_get(url, timeout_s=20.0)
    if resp.status_code != 200 or not resp.content:
        return None

    try:
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*") as tf:
            tex_chunks: list[str] = []
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if not member.name.lower().endswith(".tex"):
                    continue
                if member.size <= 0 or member.size > 2_000_000:
                    continue
                f = tf.extractfile(member)
                if f is None:
                    continue
                raw = f.read()
                if not raw:
                    continue
                try:
                    decoded = raw.decode("utf-8", errors="ignore")
                except Exception:
                    decoded = raw.decode("latin-1", errors="ignore")
                tex_chunks.append(decoded)
                if len(tex_chunks) >= 12:
                    break
    except tarfile.TarError:
        return None

    if not tex_chunks:
        return None

    plain_chunks: list[str] = []
    for tex in tex_chunks:
        plain = _latex_to_text(tex)
        if plain and plain.strip():
            plain_chunks.append(plain)
    if not plain_chunks:
        return None

    text = _clean_full_text("\n\n".join(plain_chunks))
    if not text or not _is_fulltext_quality_sufficient(text):
        return None
    return text


def _select_best_arxiv_full_text(arxiv_id: str) -> tuple[str | None, str | None]:
    candidates: list[tuple[str, str]] = []
    html_text = _fetch_arxiv_html_full_text(arxiv_id)
    if html_text:
        candidates.append(("arxiv_html", html_text))
    pdf_text = _fetch_arxiv_pdf_full_text(arxiv_id)
    if pdf_text:
        candidates.append(("arxiv_pdf", pdf_text))
    eprint_text = _fetch_arxiv_eprint_full_text(arxiv_id)
    if eprint_text:
        candidates.append(("arxiv_eprint", eprint_text))
    if not candidates:
        return None, None

    best_source: str | None = None
    best_text: str | None = None
    best_score = -1.0
    for source, text in candidates:
        score = _score_fulltext_quality(text) + _SOURCE_QUALITY_BONUS.get(source, 0.0)
        if score > best_score:
            best_score = score
            best_source = source
            best_text = text
    return best_text, best_source


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


def _fetch_crossref_oa_candidates(doi: str) -> list[OACandidate]:
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    message = data.get("message", {}) if isinstance(data, dict) else {}
    if not isinstance(message, dict):
        return []

    licenses = message.get("license")
    license_name: str | None = None
    open_access_ok = False
    if isinstance(licenses, list) and licenses:
        first = licenses[0]
        if isinstance(first, dict):
            lic_url = first.get("URL")
            if isinstance(lic_url, str) and lic_url.strip():
                license_name = lic_url.strip()
                open_access_ok = True

    candidates: list[OACandidate] = []
    links = message.get("link")
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            href = link.get("URL")
            if not isinstance(href, str) or not href.strip():
                continue
            ctype = str(link.get("content-type") or "").lower()
            if "pdf" in ctype or href.lower().endswith(".pdf"):
                candidates.append(
                    OACandidate(
                        url=href.strip(),
                        source="crossref_pdf",
                        is_pdf=True,
                        open_access_ok=open_access_ok,
                        license_name=license_name,
                    )
                )

    landing = message.get("URL")
    if isinstance(landing, str) and landing.strip():
        candidates.append(
            OACandidate(
                url=landing.strip(),
                source="crossref_landing",
                is_pdf=False,
                open_access_ok=open_access_ok,
                license_name=license_name,
            )
        )
    return candidates


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


def _fetch_openalex_oa_candidates(doi: str) -> list[OACandidate]:
    url = f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='')}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, dict):
        return []

    is_oa = bool(data.get("is_oa"))
    oa = data.get("open_access") if isinstance(data.get("open_access"), dict) else {}
    oa_license = oa.get("license") if isinstance(oa, dict) else None
    license_name = str(oa_license) if isinstance(oa_license, str) and oa_license else None

    locations: list[dict[str, Any]] = []
    for key in ("best_oa_location", "primary_location"):
        loc = data.get(key)
        if isinstance(loc, dict):
            locations.append(loc)
    oa_locations = data.get("locations")
    if isinstance(oa_locations, list):
        for loc in oa_locations:
            if isinstance(loc, dict):
                locations.append(loc)

    candidates: list[OACandidate] = []
    for loc in locations:
        pdf_url = loc.get("pdf_url") or loc.get("url_for_pdf")
        if isinstance(pdf_url, str) and pdf_url.strip():
            candidates.append(
                OACandidate(
                    url=pdf_url.strip(),
                    source="openalex_pdf",
                    is_pdf=True,
                    open_access_ok=is_oa,
                    license_name=license_name,
                )
            )
        landing_url = (
            loc.get("landing_page_url")
            or loc.get("url")
            or loc.get("url_for_landing_page")
        )
        if isinstance(landing_url, str) and landing_url.strip():
            candidates.append(
                OACandidate(
                    url=landing_url.strip(),
                    source="openalex_landing",
                    is_pdf=False,
                    open_access_ok=is_oa,
                    license_name=license_name,
                )
            )
    return candidates


def _fetch_unpaywall_record(doi: str) -> dict[str, Any] | None:
    settings = get_settings()
    email = settings.unpaywall_email or settings.email_from_address
    if not email:
        return None

    url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}?email={quote(email)}"
    resp = _http_get(url)
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _parse_unpaywall_candidates(data: dict[str, Any]) -> list[OACandidate]:
    is_oa = bool(data.get("is_oa"))
    locations: list[dict[str, Any]] = []

    best = data.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)

    extras = data.get("oa_locations")
    if isinstance(extras, list):
        for loc in extras:
            if isinstance(loc, dict):
                locations.append(loc)

    candidates: list[OACandidate] = []
    seen: set[tuple[str, str]] = set()
    for loc in locations:
        license_name = (
            str(loc.get("license")) if isinstance(loc.get("license"), str) else None
        )

        pdf_url = loc.get("url_for_pdf")
        if isinstance(pdf_url, str) and pdf_url.strip():
            key = (pdf_url.strip(), "pdf")
            if key not in seen:
                seen.add(key)
                candidates.append(
                    OACandidate(
                        url=pdf_url.strip(),
                        source="unpaywall_pdf",
                        is_pdf=True,
                        open_access_ok=is_oa,
                        license_name=license_name,
                    )
                )

        landing_url = loc.get("url_for_landing_page")
        if isinstance(landing_url, str) and landing_url.strip():
            key = (landing_url.strip(), "landing")
            if key not in seen:
                seen.add(key)
                candidates.append(
                    OACandidate(
                        url=landing_url.strip(),
                        source="unpaywall_landing",
                        is_pdf=False,
                        open_access_ok=is_oa,
                        license_name=license_name,
                    )
                )

    return candidates


def _fetch_landing_page_text(
    url: str,
    *,
    open_access_ok: bool,
) -> tuple[str | None, str]:
    if not open_access_ok:
        return None, "not_found"

    resp = _http_get(url, timeout_s=20.0)
    if resp.status_code in (401, 402, 403):
        return None, "paywalled"
    if resp.status_code != 200:
        return None, "not_found"

    text = _clean_full_text(resp.text)
    if not text:
        return None, "not_found"
    if not _is_fulltext_quality_sufficient(text):
        return None, "not_found"
    return text, "ok"


def _try_oa_candidates(candidates: list[OACandidate]) -> tuple[str | None, str | None, str | None]:
    pdf_candidates = [c for c in candidates if c.is_pdf]
    landing_candidates = [c for c in candidates if not c.is_pdf]

    for c in pdf_candidates:
        if not c.open_access_ok:
            continue
        text = _fetch_pdf_text(c.url)
        if text:
            return text, c.source, c.license_name

    for c in landing_candidates:
        text, status = _fetch_landing_page_text(c.url, open_access_ok=c.open_access_ok)
        if text and status == "ok":
            return text, c.source, c.license_name

    return None, None, None


def _extract_item_text(
    item: dict[str, Any],
) -> tuple[str | None, str, str | None, str | None, str | None]:
    arxiv_id = item.get("arxiv_id")
    doi = item.get("doi")
    url = item.get("url")
    canonical_url = item.get("canonical_url")

    if isinstance(arxiv_id, str) and arxiv_id.strip():
        aid = arxiv_id.strip()
        full_text, full_source = _select_best_arxiv_full_text(aid)
        if full_text and full_source:
            return full_text, "ok", full_source, _KIND_FULLTEXT, "arxiv"

        abstract = _fetch_arxiv_abstract(aid)
        if abstract:
            return abstract, "ok", "arxiv_api", _KIND_ABSTRACT, "arxiv"

    if isinstance(doi, str) and doi.strip():
        d = doi.strip()

        unpaywall = _fetch_unpaywall_record(d)
        if unpaywall:
            text, source, license_name = _try_oa_candidates(_parse_unpaywall_candidates(unpaywall))
            if text and source:
                return text, "ok", source, _KIND_FULLTEXT, license_name

        text, source, license_name = _try_oa_candidates(_fetch_openalex_oa_candidates(d))
        if text and source:
            return text, "ok", source, _KIND_FULLTEXT, license_name

        text, source, license_name = _try_oa_candidates(_fetch_crossref_oa_candidates(d))
        if text and source:
            return text, "ok", source, _KIND_FULLTEXT, license_name

        abstract = _fetch_crossref_abstract(d)
        if abstract:
            return abstract, "ok", "crossref", _KIND_ABSTRACT, None

        abstract = _fetch_openalex_abstract(d)
        if abstract:
            return abstract, "ok", "openalex", _KIND_ABSTRACT, None

    landing = canonical_url if isinstance(canonical_url, str) and canonical_url else url
    if isinstance(landing, str) and landing:
        open_access_ok = "arxiv.org" in landing
        text, status = _fetch_landing_page_text(landing, open_access_ok=open_access_ok)
        if text:
            return text, "ok", "landing_page", _KIND_FULLTEXT, None
        return None, status, "landing_page", None, None

    return None, "not_found", None, None, None


def _extract_item_text_and_image(
    item: dict[str, Any],
) -> tuple[str | None, str, str | None, str | None, str | None, str | None]:
    text, status, source, kind, license_name = _extract_item_text(item)
    image_url: str | None = None
    arxiv_id = item.get("arxiv_id")
    if isinstance(arxiv_id, str) and arxiv_id.strip():
        image_url = _fetch_arxiv_html_image_url(arxiv_id.strip())
    return text, status, source, kind, license_name, image_url


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

    with conn.cursor(row_factory=dict_row) as cur:
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
              i.full_text_status,
              i.full_text_kind,
              i.full_text_license,
              i.image_url
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
    kind: str | None,
    license_name: str | None,
    image_url: str | None,
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
                full_text_kind = %s,
                full_text_license = %s,
                image_url = COALESCE(items.image_url, %s),
                full_text_error = %s,
                full_text_fetched_at = %s,
                updated_at = now()
            WHERE id = %s;
            """,
            (full_text, status, source, kind, license_name, image_url, error_message, now_utc, item_id),
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
            text, status, source, kind, license_name, extracted_image_url = _extract_item_text_and_image(item)
            existing_image = item.get("image_url")
            should_backfill_image = not (
                isinstance(existing_image, str) and existing_image.strip()
            )
            image_url = extracted_image_url if should_backfill_image else None
            if text:
                hydrated += 1
                _update_item_hydration(
                    conn,
                    item_id=item_id,
                    full_text=text,
                    status="ok",
                    source=source,
                    kind=kind,
                    license_name=license_name,
                    image_url=image_url,
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
                    kind=kind,
                    license_name=license_name,
                    image_url=image_url,
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
                kind=None,
                license_name=None,
                image_url=None,
                error_message=str(exc)[:4000],
                now_utc=now_utc,
            )

    return HydratePaperTextResult(
        items_scanned=len(items),
        items_hydrated=hydrated,
        items_failed=failed,
        items_skipped=skipped,
    )
