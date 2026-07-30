#!/usr/bin/env python
"""Audit what is actually stored, not what the extractors do to fixtures.

Fixtures are frozen; publishers change their templates. And most of this
project's extraction faults were silent — mangled MathML looked like
mathematics, axis-tick rows looked like section headings — so nothing errored
and the pipeline reported success while storing corrupt text.

Two things here that the fixture audit cannot do:

- checks run against the stored rows generation will actually consume;
- per-path distributions are compared, because several faults were visible as
  statistics long before anyone read the output. Junk headings showed up as the
  PDF path averaging eighty sections against LaTeXML's twenty-three.

    python scripts/v2_corpus_audit.py [--limit N] [--path arxiv_pdf] [--verbose]

Exits non-zero if any check FAILs.
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import psycopg

# Text that must never reach an explanation.
BOILERPLATE = (
    "skip to main content",
    "accept all cookies",
    "sign up for our newsletter",
    "javascript is disabled",
)
_HTML_TAG = re.compile(
    r"<\s*/?\s*(?:div|span|p|a|img|script|table|tr|td|br)(?:\s[^<>]*)?\s*/?>", re.I
)
_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|nbsp|#\d+);")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MOJIBAKE = re.compile(r"â€[™œ\x9d“”]|Ã[©¨¡³±¼\x83]|ï»¿")
# Flattened MathML: a function name spelt as separate elements.
_LETTER_SPACED = re.compile(r"\b(?:[a-z] ){2,}[a-z]\b")
_REAL_WORD = re.compile(r"[A-Za-z]{3,}")

# An item whose heading density is far from its own path's median is either
# mis-parsed or a document shape worth knowing about.
OUTLIER_MULTIPLE = 3.0


@dataclass
class Row:
    item_id: str
    source_name: str
    path: str
    kind: str | None
    words: int
    text: str
    sections: list[dict]
    figures: list[dict]
    tables: list[dict]
    story_depths: list[str]

    @property
    def titles(self) -> list[str]:
        return [s["title"] for s in self.sections if s.get("title")]

    @property
    def sections_per_1k(self) -> float:
        return len(self.sections) / max(self.words / 1000, 0.001)


@dataclass
class Finding:
    level: str
    check: str
    detail: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def fail(self, check: str, detail: str) -> None:
        self.findings.append(Finding("FAIL", check, detail))

    def warn(self, check: str, detail: str) -> None:
        self.findings.append(Finding("WARN", check, detail))


def check_row(row: Row) -> Report:
    report = Report()
    text = row.text

    if len(_LETTER_SPACED.findall(text)) > 2:
        report.fail(
            "math-intact",
            f"letter-spaced math: {_LETTER_SPACED.findall(text)[:2]}",
        )
    if _HTML_TAG.search(text):
        report.fail("no-markup", "html tags in stored text")
    if _ENTITY.search(text):
        report.fail("no-markup", f"unescaped entity {_ENTITY.search(text).group()}")
    if _CONTROL.search(text):
        report.fail("no-control", "control characters in stored text")
    if _MOJIBAKE.search(text):
        report.fail("encoding", f"encoding damage near {_MOJIBAKE.search(text).group()!r}")
    hits = [phrase for phrase in BOILERPLATE if phrase in text.casefold()]
    if hits:
        report.fail("no-boilerplate", f"navigation furniture: {hits[0]}")

    junk = [title for title in row.titles if not _REAL_WORD.search(title)]
    if junk:
        report.fail(
            "headings",
            f"{len(junk)}/{len(row.titles)} name nothing: {junk[:2]}",
        )

    # The stored word count is what ranking and the gate read; if it disagrees
    # with the text beside it, one of them is lying.
    actual = len(text.split())
    if row.words and abs(actual - row.words) > max(20, row.words * 0.02):
        report.fail("word-count", f"stored {row.words}, text has {actual}")

    # Consumer invariant: Technical must cite what it draws on, so a story
    # offering Technical needs citable structure behind it.
    if "technical" in row.story_depths:
        if not row.titles:
            report.fail("technical-citable", "offers Technical with no named section")
        unlabelled = [
            f for f in (row.figures + row.tables) if not (f or {}).get("label")
        ]
        if len(unlabelled) > max(2, (len(row.figures) + len(row.tables)) // 2):
            report.warn(
                "technical-citable",
                f"{len(unlabelled)} floats have no label to cite",
            )

    return report


def check_distributions(rows: list[Row]) -> list[Finding]:
    """Compare each item against its own path, and each path against the rest.

    A fault that affects a whole path shows as the path's median drifting; a
    fault affecting one document shows as that item standing away from its
    peers. Neither needs anyone to read the text.
    """

    findings: list[Finding] = []
    by_path: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        # Density is a ratio, so a very short document trivially scores high:
        # one section in eight words reads as 125 per thousand.
        if row.sections and row.words >= 300:
            by_path[row.path].append(row)

    for path, group in sorted(by_path.items()):
        if len(group) < 4:
            continue
        densities = [row.sections_per_1k for row in group]
        median = statistics.median(densities)
        if median <= 0:
            continue
        for row in group:
            if row.sections_per_1k > median * OUTLIER_MULTIPLE:
                findings.append(
                    Finding(
                        "WARN",
                        "heading-density",
                        f"{row.source_name}: {row.sections_per_1k:.1f} sections/1k words "
                        f"vs {path} median {median:.1f}",
                    )
                )
    return findings


def load_rows(connection: psycopg.Connection, limit: int, path: str | None) -> list[Row]:
    clause = "AND i.full_text_source = %s" if path else ""
    parameters: tuple[object, ...] = (path, limit) if path else (limit,)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
              i.id::text, src.name, i.full_text_source, i.full_text_kind,
              COALESCE(i.full_text_words, 0), i.full_text, i.text_structure,
              COALESCE(
                (
                  SELECT array_agg(DISTINCT d)
                  FROM story_items si2
                  JOIN stories s2 ON s2.id = si2.story_id
                  CROSS JOIN LATERAL unnest(s2.supported_depths) AS d
                  WHERE si2.item_id = i.id
                ),
                '{{}}'
              )
            FROM items i
            JOIN sources src ON src.id = i.source_id
            WHERE i.full_text_status = 'ok' AND i.full_text IS NOT NULL
            {clause}
            ORDER BY i.full_text_fetched_at DESC NULLS LAST
            LIMIT %s;
            """,
            parameters,
        )
        rows = []
        for record in cursor:
            structure = record[6] or {}
            rows.append(
                Row(
                    item_id=record[0],
                    source_name=record[1],
                    path=record[2] or "unknown",
                    kind=record[3],
                    words=record[4],
                    text=record[5] or "",
                    sections=structure.get("sections") or [],
                    figures=structure.get("figures") or [],
                    tables=structure.get("tables") or [],
                    story_depths=list(record[7] or []),
                )
            )
        return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--path", help="restrict to one extraction path")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL"),
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")

    with psycopg.connect(args.database_url) as connection:
        rows = load_rows(connection, args.limit, args.path)
    if not rows:
        print("no stored text to audit")
        return 0

    failures = warnings = 0
    for row in rows:
        report = check_row(row)
        if not report.findings and not args.verbose:
            continue
        worst = "FAIL" if any(f.level == "FAIL" for f in report.findings) else (
            "warn" if report.findings else "ok"
        )
        print(
            f"[{worst:4s}] {row.source_name[:24]:24s} {row.path:14s} "
            f"{row.words:>6,}w {len(row.sections):>3d}sec"
        )
        for finding in report.findings:
            print(f"         {finding.level:4s} {finding.check:18s} {finding.detail}")
            if finding.level == "FAIL":
                failures += 1
            else:
                warnings += 1

    print("\nper-path distribution")
    print(f"  {'path':16s} {'items':>5s} {'med words':>10s} {'med sec/1k':>11s}")
    by_path: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_path[row.path].append(row)
    for path, group in sorted(by_path.items()):
        words = statistics.median(r.words for r in group)
        density = statistics.median(
            [r.sections_per_1k for r in group if r.sections] or [0]
        )
        print(f"  {path:16s} {len(group):>5d} {words:>10,.0f} {density:>11.1f}")

    for finding in check_distributions(rows):
        print(f"  {finding.level:4s} {finding.check:18s} {finding.detail}")
        warnings += 1

    print(f"\n{len(rows)} stored items audited: {failures} failures, {warnings} warnings")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
