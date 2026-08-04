"""Rewrite the Glances a reader could not follow.

231 of 966 published Glances need the field to read. The judge that found them
now gates new writing, and present-v9 carries the instruction that beat the old
one: a technical term may appear only in a sentence that also says what it is,
and that rule does not buy extra sentences.

Only the Glance is rewritten. Regenerating the whole presentation would cost
about eleven cents a story and would also replace an Explain and a Technical
that passed their own gates — there is no reason to spend money making those
different.

Every rewrite is judged before it is stored, by the same judge that gates
production, and a rewrite that fails is retried once. Measured over 50 stories
the instruction rescues 31 of 34, so a second attempt should clear most of the
remainder; anything still failing keeps the Glance it had and is reported, so
the ones needing a human are a list rather than a silence.

Resumable and idempotent: only Glances currently carrying a failing verdict are
touched, and a stored rewrite carries its own fresh verdict.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.generation import present as present_module
from curious_now_v2.generation.client import CodexGenerator
from curious_now_v2.generation.readable import PROMPT_VERSION, judge_readability

WORKERS = 6
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None
URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]

GLANCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["glance"],
    "properties": {"glance": {"type": "string"}},
}

# The Glance instruction from present-v9, reduced to the one rung being
# rewritten. It has to say the same things in the same words: a story's Glance
# should not depend on which pass produced it.
PROMPT = """You are writing for Curious Now, a calm feed of science worth \
understanding.

Everything you write must stay inside the CLAIMS below. Do not add anything \
they do not carry, and do not use outside knowledge.

Write the Glance: 25 to 150 words, for someone curious with no background in \
this field — imagine a sharp friend who works in something else.

ONE idea. Decide the single thing this reader should walk away knowing, say it \
plainly, give them one way to picture it or one reason to believe it, and say \
why it might matter. Then stop.

Where the evidence carries a qualification, write it into the Glance as part of \
the explanation — a clause in the reader's path, not a disclaimer at the end.

One rule governs every technical term, and it is absolute: a term may appear \
only in a sentence that also says what it is.

  wrong   Polar domains organize, then fragment below the transition.
  right   Regions where the crystal's charges line up — polar domains — grow
          orderly as it cools, then break up.

  wrong   The method improves the lithium-ion transference number.
  right   More of the current is carried by the lithium itself rather than by
          the other ions drifting the wrong way.

If saying what a term is would cost more words than the idea is worth, the term \
does not belong in the Glance at all. Say the finding without it. Before you \
answer, read your Glance back and find any noun phrase a reader would have to \
look up. If there is one, you have not finished.

That rule does not buy you extra sentences. You still have ONE idea, and you \
still stop. Three or four sentences is the shape of a Glance; if you find \
yourself writing a fifth, you have started a second idea. A Glance that \
explains four things clearly has failed as surely as one that explains nothing: \
the reader was handed a lecture where they came for an idea. So the trade runs \
one way — explaining a term is worth sentences, and adding a second finding \
never is.

TITLE: {title}

CLAIMS:
{claims}
"""


def pending() -> list[tuple]:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id, e.id, COALESCE(dt.text, s.working_title)
            FROM stories s
            JOIN explanations e ON e.story_id = s.id
              AND e.evidence_packet_id = s.current_evidence_packet_id
              AND e.depth = 'glance'
            LEFT JOIN display_titles dt
              ON dt.id = s.current_display_title_id AND dt.status = 'valid'
            WHERE s.status = 'published'
              AND e.content->'readability'->>'verdict' = 'needs_the_field'
            ORDER BY s.id
            {"LIMIT %s" if LIMIT else ""};
            """,
            (LIMIT,) if LIMIT else (),
        )
        return list(cur.fetchall())


generator = CodexGenerator()
targets = pending()
print(f"{len(targets)} glances a reader could not follow\n")


def one(target: tuple) -> tuple[str, float]:
    story_id, explanation_id, title = target
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT ec.claim_kind, ec.claim_text FROM evidence_claims ec
               JOIN evidence_packets ep ON ep.id = ec.evidence_packet_id
               JOIN stories s ON s.current_evidence_packet_id = ep.id
               WHERE s.id = %s ORDER BY ec.ordinal LIMIT 10;""",
            (story_id,),
        )
        claims = "\n".join(f"[{k}] {t}" for k, t in cur.fetchall())

    if not claims:
        return "no claims", 0.0

    spend = 0.0
    prompt = PROMPT.format(title=title or "", claims=claims)
    best: tuple[str, object] | None = None

    # Two attempts. The instruction clears 31 of 34 on one, so a second covers
    # most of the rest without paying for a third on every story.
    for _ in range(2):
        completion = generator.complete(prompt, GLANCE_SCHEMA, timeout=240)
        spend += completion.usage.cost(generator.model)
        text = str((completion.payload or {}).get("glance") or "").strip()
        if not text:
            continue
        problems = present_module.validate_glance_words(text)
        if problems:
            continue
        judged = judge_readability(generator, title=title or "", glance=text)
        spend += judged.completion.usage.cost(generator.model)
        best = (text, judged)
        if judged.plain:
            break

    if best is None:
        return "no usable rewrite", spend

    text, judged = best
    if not judged.plain:
        # Kept rather than swapped: replacing one unreadable Glance with
        # another spends money to change nothing, and the old one at least
        # carries the verdict that found it.
        return "still failing", spend

    with psycopg.connect(URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE explanations
               SET plain_text = %s,
                   content = COALESCE(content, '{}'::jsonb) || %s,
                   prompt_version = %s,
                   status = 'valid',
                   validated_at = now()
             WHERE id = %s;
            """,
            (
                text,
                Jsonb(
                    {
                        "readability": {
                            "verdict": judged.verdict,
                            "blocking_phrase": "",
                            "reason": judged.reason,
                            "judge_version": PROMPT_VERSION,
                        },
                        "rewritten_from": "present-v8-or-earlier",
                    }
                ),
                present_module.PROMPT_VERSION,
                explanation_id,
            ),
        )
    return "rewritten", spend


done: Counter[str] = Counter()
spend = 0.0
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for index, (outcome, cost) in enumerate(pool.map(one, targets), start=1):
        done[outcome] += 1
        spend += cost
        if index % 25 == 0:
            print(f"  {index}/{len(targets)}  ${spend:.2f}  "
                  f"{done['rewritten']} rewritten", flush=True)

total = sum(done.values()) or 1
print(f"\nUS${spend:.2f}")
for outcome, n in done.most_common():
    print(f"  {n:5d}  {outcome}  ({100 * n // total}%)")
