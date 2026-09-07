#!/usr/bin/env python
"""Measure whether the published feed covers every configured field.

Coverage means useful volume from genuinely different publishing origins, not
several topical feeds from the same outlet. By default a field is covered with
ten published stories from three origins. An origin supplying more than 60% is
reported separately as a balance warning: it should not make a large, diverse
field such as AI look absent.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

ROOT = Path(__file__).resolve().parents[1]
FIELDS_PATH = ROOT / "config" / "v2" / "fields.json"


@dataclass(frozen=True)
class Coverage:
    stories: int
    origins: int
    top_origin: str | None
    top_share: float


def source_origin(homepage_url: str | None, source_name: str) -> str:
    """The outlet behind a feed; topical feeds must not simulate diversity."""

    host = urlsplit(homepage_url or "").hostname
    if not host:
        return source_name
    return host.removeprefix("www.").casefold()


def configured_fields(path: Path = FIELDS_PATH) -> tuple[tuple[str, str], ...]:
    data = json.loads(path.read_text())
    return tuple(
        (leaf["slug"], leaf["label"])
        for group in data["groups"]
        for leaf in group["leaves"]
    )


def load_coverage(database_url: str) -> dict[str, Coverage]:
    field_stories: dict[str, set[object]] = defaultdict(set)
    field_origins: dict[str, dict[str, set[object]]] = defaultdict(
        lambda: defaultdict(set)
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT st.field, st.id, src.name, src.homepage_url
            FROM stories st
            JOIN story_items si ON si.story_id = st.id
            JOIN items i ON i.id = si.item_id
            JOIN sources src ON src.id = i.source_id
            WHERE st.status = 'published' AND st.field IS NOT NULL;
            """
        )
        for field, story_id, source_name, homepage_url in cursor:
            origin = source_origin(homepage_url, source_name)
            field_stories[field].add(story_id)
            field_origins[field][origin].add(story_id)

    result: dict[str, Coverage] = {}
    for field, story_ids in field_stories.items():
        counts = Counter(
            {origin: len(ids) for origin, ids in field_origins[field].items()}
        )
        top_origin, top_count = counts.most_common(1)[0]
        result[field] = Coverage(
            stories=len(story_ids),
            origins=len(counts),
            top_origin=top_origin,
            top_share=top_count / len(story_ids),
        )
    return result


def coverage_failures(
    coverage: Coverage,
    *,
    min_stories: int,
    min_origins: int,
) -> tuple[str, ...]:
    reasons = []
    if coverage.stories < min_stories:
        reasons.append(f"stories<{min_stories}")
    if coverage.origins < min_origins:
        reasons.append(f"origins<{min_origins}")
    return tuple(reasons)


def balance_warnings(
    coverage: Coverage,
    *,
    max_top_share: float,
) -> tuple[str, ...]:
    if coverage.stories and coverage.top_share > max_top_share:
        return (f"top>{max_top_share:.0%}",)
    return ()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    parser.add_argument("--min-stories", type=int, default=10)
    parser.add_argument("--min-origins", type=int, default=3)
    parser.add_argument("--max-top-share", type=float, default=0.60)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")
    if args.min_stories < 1 or args.min_origins < 1:
        raise SystemExit("minimums must be positive")
    if not 0 < args.max_top_share <= 1:
        raise SystemExit("--max-top-share must be between 0 and 1")

    measured = load_coverage(args.database_url)
    empty = Coverage(stories=0, origins=0, top_origin=None, top_share=0)
    gap_count = 0
    warning_count = 0
    print(
        f"{'field':29s} {'stories':>7s} {'origins':>7s} "
        f"{'top':>6s} {'top origin':24s}  result"
    )
    for slug, label in configured_fields():
        coverage = measured.get(slug, empty)
        gaps = coverage_failures(
            coverage,
            min_stories=args.min_stories,
            min_origins=args.min_origins,
        )
        warnings = balance_warnings(
            coverage,
            max_top_share=args.max_top_share,
        )
        gap_count += bool(gaps)
        warning_count += bool(warnings)
        top = f"{coverage.top_share:.0%}" if coverage.stories else "-"
        top_origin = (coverage.top_origin or "-")[:24]
        result = ", ".join(gaps) if gaps else "pass"
        if warnings:
            result += f"; balance warning: {', '.join(warnings)}"
        print(
            f"{label[:29]:29s} {coverage.stories:7d} "
            f"{coverage.origins:7d} {top:>6s} {top_origin:24s}  {result}"
        )

    print(
        f"\n{len(configured_fields()) - gap_count}/{len(configured_fields())} "
        f"fields meet coverage; {gap_count} gaps and "
        f"{warning_count} balance warnings remain"
    )
    return 1 if gap_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
