"""Give already-published stories the field their packet never asked for.

Everything generated under packet-v4 and earlier predates the `field` key, so
974 stories carry nothing. Re-running generation for them would cost a hundred
dollars and rewrite prose that is already correct; this asks the one question
they are missing.

It does not need the document. The title, the central claim and a few claims
are already stored, and they are what decides a field -- so this is a small
call per story rather than a re-read, which is why it costs about five dollars
where generation cost a hundred.

Both paths share `curious_now_v2.core.fields`, so the leaf a backfilled story
gets and the leaf a freshly generated one gets come from the same list. If they
were written separately, a story's field would depend on when it was ingested.

Resumable: only stories with no field are asked about, so it can be stopped and
restarted. Idempotent for the same reason.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg

from curious_now_v2.core.fields import describe_for_prompt, leaf, leaf_slugs
from curious_now_v2.generation.client import CodexGenerator

WORKERS = 8

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["field"],
    "properties": {
        "field": {"type": "string", "enum": [*leaf_slugs(), "unclear"]},
    },
}

# Deliberately the same three rules as the packet prompt. They are what decides
# the awkward cases, and the awkward cases are where two prompts drift.
PROMPT = """What field of science is this work in? Choose one:

{field_list}

Three rules decide the awkward cases, and they matter more than the labels:

- The field is where the FINDING lands, not what the method was. A neural
  network that predicts protein folding is molecular_cell_biology. A method
  paper benchmarked on piano recordings is ai, because what it establishes is
  about the method.
- If the finding is about the nervous system, it is neuroscience, not
  molecular_cell_biology. Clinical mental illness is mental_health; basic
  research on behaviour and cognition is psychology or cognitive_science.
- quantum_computing is computing, not physics.

Choose "unclear" only when this genuinely does not establish a subject.
Guessing puts a physics paper in front of someone who asked for medicine.

TITLE: {title}

WHAT IT AMOUNTS TO: {central}

CLAIMS:
{claims}
"""

URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None


def pending() -> list[tuple]:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id,
                   COALESCE(dt.text, s.working_title),
                   COALESCE(ep.central_claim, '')
            FROM stories s
            LEFT JOIN display_titles dt
              ON dt.id = s.current_display_title_id AND dt.status = 'valid'
            LEFT JOIN evidence_packets ep ON ep.id = s.current_evidence_packet_id
            WHERE s.status = 'published' AND s.field IS NULL
            ORDER BY s.id
            {"LIMIT %s" if LIMIT else ""};
            """,
            (LIMIT,) if LIMIT else (),
        )
        return list(cur.fetchall())


generator = CodexGenerator()
targets = pending()
print(f"{len(targets)} published stories carry no field\n")


def one(target: tuple) -> tuple[str | None, float]:
    story_id, title, central = target
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT ec.claim_text FROM evidence_claims ec
               JOIN evidence_packets ep ON ep.id = ec.evidence_packet_id
               JOIN stories s ON s.current_evidence_packet_id = ep.id
               WHERE s.id = %s ORDER BY ec.ordinal LIMIT 4;""",
            (story_id,),
        )
        claims = "\n".join(f"- {text}" for (text,) in cur.fetchall())

    completion = generator.complete(
        PROMPT.format(
            field_list=describe_for_prompt(),
            title=title or "",
            central=central,
            claims=claims,
        ),
        SCHEMA,
        timeout=180,
    )
    answer = str((completion.payload or {}).get("field") or "").strip()
    # "unclear" is stored as NULL, not as a leaf: the column's absence already
    # means "not established", and a story tagged `unclear` would otherwise need
    # every reader to know it is not a field.
    chosen = answer if leaf(answer) else None

    if chosen:
        with psycopg.connect(URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE stories SET field = %s, updated_at = now() WHERE id = %s;",
                (chosen, story_id),
            )
    return chosen, completion.usage.cost(generator.model)


done = Counter()
spend = 0.0
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for index, (chosen, cost) in enumerate(pool.map(one, targets), start=1):
        done[chosen or "unclear"] += 1
        spend += cost
        if index % 50 == 0:
            print(f"  {index}/{len(targets)}  ${spend:.2f}")

print(f"\ntagged {sum(done.values()) - done['unclear']}, "
      f"left unclear {done['unclear']}; US${spend:.2f}\n")
for slug, n in done.most_common():
    entry = leaf(slug)
    print(f"  {n:4d}  {slug:24s} {entry.group_label if entry else '(no field)'}")
