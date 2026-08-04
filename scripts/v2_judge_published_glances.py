"""Run the Glance judge over what is already published.

The judge now guards new writing, but 974 stories went out before it existed,
under a prompt that asked for a reader with no background in the field and a
validator that only counted words. Sampled at 140, 9% needed the field to read
and 11% opened by referring to something never introduced.

This finds them. It does not regenerate them: rewriting a Glance means running
the whole presentation pass again over the source document, which is the
expensive call, and how many are worth that is a decision to take with the
number in hand rather than before it.

What it does do is stop shipping a Glance a reader cannot follow. A story whose
Glance fails has that rung withheld — the explanation row is marked, and
supported_depths loses 'glance' — so the reader gets Explain and Technical
rather than a compressed abstract wearing the label "The idea". That is the
same rule the pipeline now applies to new writing.

Resumable: a Glance already carrying a verdict is skipped.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.generation.client import CodexGenerator
from curious_now_v2.generation.readable import PROMPT_VERSION, judge_readability

WORKERS = 8
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None
WITHHOLD = os.environ.get("WITHHOLD_FAILURES") == "1"
URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]


def pending() -> list[tuple]:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id, e.id, COALESCE(dt.text, s.working_title), e.plain_text
            FROM stories s
            JOIN explanations e ON e.story_id = s.id
              AND e.evidence_packet_id = s.current_evidence_packet_id
              AND e.depth = 'glance' AND e.status = 'valid'
            LEFT JOIN display_titles dt
              ON dt.id = s.current_display_title_id AND dt.status = 'valid'
            WHERE s.status = 'published'
              AND e.plain_text IS NOT NULL
              AND NOT COALESCE(e.content ? 'readability', false)
            ORDER BY s.id
            {"LIMIT %s" if LIMIT else ""};
            """,
            (LIMIT,) if LIMIT else (),
        )
        return list(cur.fetchall())


generator = CodexGenerator()
targets = pending()
print(f"{len(targets)} published glances with no verdict")
print(f"withholding failures: {'yes' if WITHHOLD else 'no (judging only)'}\n")


def one(target: tuple) -> tuple[str, float]:
    story_id, explanation_id, title, glance = target
    judged = judge_readability(generator, title=title or "", glance=glance)
    cost = judged.completion.usage.cost(generator.model)
    if not judged.completion.ok:
        return "errored", cost

    with psycopg.connect(URL, autocommit=True) as conn, conn.cursor() as cur:
        # Recorded on the explanation rather than in a table of its own: the
        # verdict is about this text, and a regenerated Glance must not inherit
        # the judgement of the one it replaced.
        cur.execute(
            """
            UPDATE explanations
               SET content = COALESCE(content, '{}'::jsonb) || %s
             WHERE id = %s;
            """,
            (
                Jsonb(
                    {
                        "readability": {
                            "verdict": judged.verdict,
                            "blocking_phrase": judged.blocking_phrase,
                            "reason": judged.reason,
                            "judge_version": PROMPT_VERSION,
                        }
                    }
                ),
                explanation_id,
            ),
        )
        if judged.plain:
            return "plain", cost

        if WITHHOLD:
            # 'invalid' rather than a new status: the table's check constraint
            # allows pending, valid, invalid, failed and superseded, and this is
            # a Glance that did not meet the contract — which is what invalid
            # already means everywhere else in the pipeline.
            cur.execute(
                "UPDATE explanations SET status = 'invalid' WHERE id = %s;",
                (explanation_id,),
            )
            cur.execute(
                """UPDATE stories
                      SET supported_depths = array_remove(supported_depths, 'glance'),
                          updated_at = now()
                    WHERE id = %s;""",
                (story_id,),
            )
    return "needs_the_field", cost


done: Counter[str] = Counter()
spend = 0.0
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for index, (outcome, cost) in enumerate(pool.map(one, targets), start=1):
        done[outcome] += 1
        spend += cost
        if index % 100 == 0:
            print(f"  {index}/{len(targets)}  ${spend:.2f}  "
                  f"{done['needs_the_field']} failing")

total = sum(done.values()) or 1
print(f"\nUS${spend:.2f}")
for outcome, n in done.most_common():
    print(f"  {n:5d}  {outcome}  ({100 * n // total}%)")

with psycopg.connect(URL) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT e.content->'readability'->>'blocking_phrase'
        FROM explanations e
        WHERE e.content->'readability'->>'verdict' = 'needs_the_field'
        LIMIT 400;
        """
    )
    phrases = [p for (p,) in cur.fetchall() if p]

if phrases:
    print("\nWHAT BLOCKS A READER, IN OUR OWN WORDS")
    for phrase, n in Counter(phrases).most_common(15):
        print(f"  {n:3d}  {phrase[:76]}")
