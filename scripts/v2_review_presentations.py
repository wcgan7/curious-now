#!/usr/bin/env python
"""Print what a reader would actually meet, for human review.

Every other check in this repo asks whether output satisfies a rule. This one
exists because the faults that matter most — a Glance that reads as a
compressed abstract, a caveat that reads as boilerplate — are invisible to
rules and obvious to a person. So it prints the layers as prose, in ladder
order, and gets out of the way.

    PYTHONPATH=. python scripts/v2_review_presentations.py [--limit N] [--marks]

`--marks` underlines the span the writer claims carries the qualification, to
check it is written into the reader's path rather than appended to it.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap

import psycopg

WIDTH = 84
DIM, BOLD, UNDER, OFF = "\033[2m", "\033[1m", "\033[4m", "\033[0m"


def wrap(text: str, indent: str = "  ") -> str:
    return "\n".join(
        textwrap.fill(
            paragraph, WIDTH, initial_indent=indent, subsequent_indent=indent
        )
        for paragraph in text.split("\n")
        if paragraph.strip()
    )


def mark(text: str, span: str) -> str:
    """Underline the qualification where it sits in the prose."""

    if not span:
        return text
    at = text.casefold().find(span.casefold())
    if at < 0:
        return text
    return f"{text[:at]}{UNDER}{text[at : at + len(span)]}{OFF}{text[at + len(span) :]}"


QUERY = """
SELECT
  src.name,
  ep.provenance->>'story_kind',
  dt.text,
  sp.novelty,
  sp.essential_qualification,
  (SELECT plain_text FROM explanations
   WHERE story_id = s.id AND evidence_packet_id = ep.id
     AND depth = 'glance' AND status = 'valid'),
  (SELECT content->>'qualification_span' FROM explanations
   WHERE story_id = s.id AND evidence_packet_id = ep.id
     AND depth = 'glance' AND status = 'valid'),
  (SELECT plain_text FROM explanations
   WHERE story_id = s.id AND evidence_packet_id = ep.id
     AND depth = 'explain' AND status = 'valid'),
  (SELECT failure_reason FROM explanations
   WHERE story_id = s.id AND evidence_packet_id = ep.id
     AND depth = 'explain' AND status <> 'valid')
FROM stories s
JOIN evidence_packets ep ON ep.id = s.current_evidence_packet_id
JOIN display_titles dt ON dt.id = s.current_display_title_id
JOIN conceptual_spines sp ON sp.evidence_packet_id = ep.id
JOIN story_items si ON si.story_id = s.id
JOIN items i ON i.id = si.item_id
JOIN sources src ON src.id = i.source_id
WHERE s.status = 'published' AND ep.status = 'valid'
ORDER BY ep.validated_at DESC NULLS LAST, s.id
LIMIT %s;
"""

WITHHELD = """
SELECT src.name, s.working_title, s.publication_reasons
FROM stories s
JOIN story_items si ON si.story_id = s.id
JOIN items i ON i.id = si.item_id
JOIN sources src ON src.id = i.source_id
WHERE s.status = 'draft' AND s.publication_reasons::text LIKE '%%withheld%%'
ORDER BY s.gated_at DESC NULLS LAST
LIMIT %s;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--marks", action="store_true",
                        help="underline the qualification inside the Glance")
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")

    with psycopg.connect(args.database_url) as connection, connection.cursor() as cur:
        cur.execute(QUERY, (args.limit,))
        rows = cur.fetchall()
        cur.execute(WITHHELD, (args.limit,))
        withheld = cur.fetchall()

    seen: set[str] = set()
    for source, kind, title, novelty, spine_qual, glance, span, explain, declined in rows:
        if title in seen:
            continue
        seen.add(title)
        print(f"\n{'─' * WIDTH}")
        print(f"{DIM}{source} · {kind}{OFF}")
        print(f"{BOLD}{title}{OFF}\n")
        if glance:
            body = mark(glance, span or "") if args.marks else glance
            print(f"{DIM}  GLANCE · new to this{OFF}")
            print(wrap(body))
            if not span:
                print(f"{DIM}  (no qualification: the evidence carried none){OFF}")
        if explain:
            print(f"\n{DIM}  EXPLAIN · know the field · {len(explain.split())} words{OFF}")
            print(wrap(explain))
        elif declined:
            print(f"\n{DIM}  EXPLAIN declined: {declined}{OFF}")
        if novelty:
            print(f"\n{DIM}  spine · novelty: {novelty}{OFF}")
        if spine_qual:
            print(f"{DIM}  spine · qualification: {spine_qual}{OFF}")

    if withheld:
        print(f"\n{'─' * WIDTH}\n{BOLD}Withheld{OFF} — kept in the database, never shown\n")
        for source, title, reasons in withheld:
            why = (reasons or ["?"])[0]
            print(f"  {DIM}{source}{OFF} {title[:52]}")
            print(f"    {DIM}{why}{OFF}")

    print(f"\n{len(seen)} shown, {len(withheld)} withheld")
    return 0


if __name__ == "__main__":
    sys.exit(main())
