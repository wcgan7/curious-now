#!/usr/bin/env python
"""Audit each source for the faults that only show up per source.

Written after a Nature book review reached the feed labelled peer reviewed. The
cause was structural rather than particular: `default_content_type` is a
property of a feed, and Nature sends research, news, comment and book reviews
down one URL. Any source can have that shape, and nothing in the pipeline
noticed — so this asks the questions that would have caught it, for every
source at once.

    PYTHONPATH=. python scripts/v2_source_audit.py [--verbose]

Four questions, in descending order of how much harm a wrong answer does:

1. Does the source claim a review status it cannot support? "Peer reviewed" and
   "Preprint" are claims about how work was vetted, and a feed default is not
   evidence about any particular item on a mixed feed.
2. Does its type route items correctly? Paper types get the open-access chain
   (arXiv, PMC, OpenAlex); everything else only ever gets its own page. A paper
   typed as news loses its free full text, and news typed as a paper spends
   third-party lookups that cannot help it.
3. Is the feed mixed? Distinct URL families are how a single feed carrying
   several kinds of thing gives itself away, and the count that reaches
   publication is what decides whether it matters.
4. Does retrieval work? Reported against what was attempted, since an untried
   backlog is not a failure and should not read as one.

Exits non-zero if any source claims a review status without evidence.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import psycopg

from curious_now_v2.db.retrieval import PAPER_TYPES

# A type that tells the reader how the work was vetted. Everything else
# describes where an item came from, which the source name already says.
REVIEW_CLAIMS = frozenset({"peer_reviewed", "preprint", "report", "dataset"})
# Enough of a foothold to be worth reporting as a family of its own.
FAMILY_FLOOR = 2


@dataclass
class Source:
    name: str
    items: int = 0
    published: int = 0
    families: Counter[str] = field(default_factory=Counter)
    published_families: Counter[str] = field(default_factory=Counter)
    types: Counter[tuple[str, str]] = field(default_factory=Counter)
    attempted: int = 0
    retrieved: int = 0
    failures: Counter[str] = field(default_factory=Counter)

    @property
    def unevidenced_claims(self) -> int:
        """Items asserting a review status on nothing but a mixed feed's default."""

        return sum(
            count
            for (content_type, basis), count in self.types.items()
            if content_type in REVIEW_CLAIMS and basis == "feed_unmatched"
        )

    @property
    def mixed_families(self) -> list[tuple[str, int]]:
        return [
            (family, count)
            for family, count in self.published_families.most_common()
            if count >= FAMILY_FLOOR
        ]

    @property
    def routes_as_paper(self) -> bool:
        return any(
            content_type in PAPER_TYPES for content_type, _ in self.types
        )


def family(url: str) -> str:
    """The first path segment, which is how publishers separate their sections."""

    parts = [part for part in urlsplit(url).path.split("/") if part]
    return parts[0] if parts else "/"


def load(connection: psycopg.Connection) -> dict[str, Source]:
    sources: dict[str, Source] = defaultdict(lambda: Source(name=""))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              s.name, i.url, i.content_type, i.content_type_basis,
              COALESCE(i.full_text_status, 'pending'), i.full_text_error,
              EXISTS (
                SELECT 1 FROM story_items si JOIN stories st ON st.id = si.story_id
                WHERE si.item_id = i.id AND st.status = 'published'
              )
            FROM items i
            JOIN sources s ON s.id = i.source_id;
            """
        )
        for name, url, content_type, basis, status, error, published in cursor:
            source = sources[name]
            source.name = name
            source.items += 1
            source.families[family(url)] += 1
            source.types[(content_type, basis)] += 1
            if published:
                source.published += 1
                source.published_families[family(url)] += 1
            if status != "pending":
                source.attempted += 1
                if status == "ok":
                    source.retrieved += 1
                else:
                    reason = status
                    if error and "too short" in error:
                        reason = "too short"
                    source.failures[reason] += 1
    return dict(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true",
                        help="show every source, not only those with findings")
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")

    with psycopg.connect(args.database_url) as connection:
        sources = load(connection)
    if not sources:
        print("no items to audit")
        return 0

    print(f"{'source':26s} {'items':>6s} {'pub':>5s} {'retrieved':>10s}  type (basis)")
    failures = 0
    for name, source in sorted(sources.items()):
        rate = (
            f"{source.retrieved}/{source.attempted}"
            if source.attempted
            else "none tried"
        )
        types = ", ".join(
            f"{content_type}({basis})"
            for (content_type, basis), _ in source.types.most_common(3)
        )
        print(
            f"{name[:26]:26s} {source.items:6d} {source.published:5d} "
            f"{rate:>10s}  {types[:44]}"
        )

        if source.unevidenced_claims:
            failures += 1
            print(f"    FAIL  {source.unevidenced_claims} items claim a review "
                  "status with nothing to support it")

        families = source.mixed_families
        if len(families) > 1:
            shown = ", ".join(f"{f}({n})" for f, n in families[:4])
            note = "routes to the paper chain" if source.routes_as_paper else ""
            print(f"    mixed feed: {len(families)} families published — {shown}"
                  f"{'; ' + note if note else ''}")

        if source.attempted and not source.retrieved:
            print(f"    nothing retrieved in {source.attempted} attempts: "
                  f"{', '.join(f'{k}:{v}' for k, v in source.failures.most_common(3))}")
        elif source.failures and args.verbose:
            print(f"    failures: "
                  f"{', '.join(f'{k}:{v}' for k, v in source.failures.most_common(4))}")

        backlog = source.items - source.attempted
        if backlog > source.attempted and backlog > 50:
            print(f"    {backlog:,} items never attempted — the rate above "
                  "describes a sample, not the source")

    print(f"\n{len(sources)} sources audited: {failures} making unevidenced claims")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
