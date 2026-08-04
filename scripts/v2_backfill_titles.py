"""Give published stories the title the new rules would have produced.

Two changes landed together and this applies both to what is already out.

**News keeps its own headline.** A judge over 140 published stories found ours
harder than the source's own on 28% of items that arrived already written for a
reader — "How AI trained on birds is surfacing underwater mysteries" had become
"Perch 2.0 Transfers Bird-Learned Sound Features to Underwater Tasks". Those
need no model at all: the headline is already in the database.

**Papers get the new prompt.** present-v8 shows the model ten real newsroom
headlines as the target register and adds one mechanical check — three nouns in
a row means it has named a technique instead of saying what happened. Blind
against the old instruction over 45 papers it was preferred 25 times to 5, and
read as plain to a non-expert 36 times against 15.

The paper half needs a model but not the document: a title comes from the
claims, which are stored. That is why this costs cents rather than the hundred
dollars a full regeneration did.

Resumable and idempotent: a story is skipped once its current title was written
by present-v8 or restored from the source.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg

from curious_now_v2.generation import present as present_module
from curious_now_v2.generation.client import CodexGenerator

WORKERS = 8
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None
URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]

TITLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title"],
    "properties": {"title": {"type": "string"}},
}

# The register instruction from present-v8, so a backfilled title and a freshly
# generated one come from the same words. Two copies would drift, and a reader
# would see which pass wrote a story.
PROMPT = """You are writing a title for Curious Now, a calm feed of science \
worth understanding. Six to fourteen words. No hype, no superlative the \
evidence does not carry, no manufactured question. Stay inside the claims \
below; do not add anything they do not support.

Write it in the register of these, which are real headlines from science \
newsrooms and research labs:

    Butterflies thrive in micro-reserve garden
    Uncovering repurposed medicines to fight liver fibrosis
    All living things emit a faint glow. Could this light be useful?
    How confessions can keep language models honest
    Deep-sea snails ride surface currents to reach distant hydrothermal vents
    Uniting biological toolkits for a new approach to ALS
    AI maps Titan's methane clouds in record time
    A new quantum toolkit for optimization
    Finding GPT-4's mistakes with GPT-4
    The anatomy of a personal health agent

Notice what they do not do: they do not name the method, they do not stack \
nouns, and they do not use an acronym a reader would have to look up. Notice \
what they do: a concrete subject, an ordinary verb, and one idea.

Then check your title against one rule before you answer: if it contains three \
nouns in a row, rewrite it. A noun stack is what a title looks like when it has \
named a technique instead of saying what happened.

PAPER'S OWN TITLE: {title}

WHAT IT AMOUNTS TO: {central}

CLAIMS:
{claims}
"""


def pending() -> list[tuple]:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id, i.title, i.content_type, COALESCE(ep.central_claim, ''),
                   COALESCE(dt.text, s.working_title)
            FROM stories s
            JOIN story_items si ON si.story_id = s.id
            JOIN items i ON i.id = si.item_id
            LEFT JOIN evidence_packets ep ON ep.id = s.current_evidence_packet_id
            LEFT JOIN display_titles dt
              ON dt.id = s.current_display_title_id AND dt.status = 'valid'
            WHERE s.status = 'published'
              AND (dt.prompt_version IS NULL OR dt.prompt_version <> %s)
            GROUP BY s.id, i.title, i.content_type, ep.central_claim,
                     dt.text, s.working_title
            ORDER BY s.id
            {"LIMIT %s" if LIMIT else ""};
            """,
            (present_module.PROMPT_VERSION, LIMIT) if LIMIT
            else (present_module.PROMPT_VERSION,),
        )
        return list(cur.fetchall())


def store(story_id, text: str, problems: tuple[str, ...]) -> None:
    with psycopg.connect(URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO display_titles (
              story_id, evidence_packet_id, conceptual_spine_id, version, text,
              status, prompt_version, model_provider, model_name, validated_at
            )
            SELECT s.id, s.current_evidence_packet_id,
                   (SELECT cs.id FROM conceptual_spines cs
                     WHERE cs.story_id = s.id ORDER BY cs.version DESC LIMIT 1),
                   (SELECT COALESCE(max(version), 0) + 1 FROM display_titles
                     WHERE story_id = s.id),
                   %s, %s, %s, 'openai', %s, now()
            FROM stories s WHERE s.id = %s
            RETURNING id;
            """,
            (
                text,
                "valid" if not problems else "invalid",
                present_module.PROMPT_VERSION,
                CodexGenerator().model,
                story_id,
            ),
        )
        row = cur.fetchone()
        if row and not problems:
            cur.execute(
                """UPDATE stories SET current_display_title_id = %s,
                          updated_at = now() WHERE id = %s;""",
                (row[0], story_id),
            )


generator = CodexGenerator()
targets = pending()
print(f"{len(targets)} published stories not yet on {present_module.PROMPT_VERSION}\n")


def one(target: tuple) -> tuple[str, float]:
    story_id, source_title, content_type, central, _current = target

    if content_type in present_module.WRITTEN_FOR_READERS:
        # No model needed: the headline was already written for a reader and is
        # sitting in the database.
        shown, problems = present_module.title_for(
            source_title=source_title, generated="", content_type=content_type
        )
        if shown and shown != "":
            store(story_id, shown, problems)
            return "restored", 0.0

    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT ec.claim_text FROM evidence_claims ec
               JOIN evidence_packets ep ON ep.id = ec.evidence_packet_id
               JOIN stories s ON s.current_evidence_packet_id = ep.id
               WHERE s.id = %s ORDER BY ec.ordinal LIMIT 6;""",
            (story_id,),
        )
        claims = "\n".join(f"- {text}" for (text,) in cur.fetchall())

    completion = generator.complete(
        PROMPT.format(title=source_title or "", central=central, claims=claims),
        TITLE_SCHEMA,
        timeout=180,
    )
    cost = completion.usage.cost(generator.model)
    written = str((completion.payload or {}).get("title") or "").strip()
    if not written:
        return "failed", cost

    shown, problems = present_module.title_for(
        source_title=source_title, generated=written, content_type=content_type
    )
    store(story_id, shown, problems)
    return ("rewritten" if not problems else "rewritten_invalid"), cost


done: Counter[str] = Counter()
spend = 0.0
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for index, (outcome, cost) in enumerate(pool.map(one, targets), start=1):
        done[outcome] += 1
        spend += cost
        if index % 100 == 0:
            print(f"  {index}/{len(targets)}  ${spend:.2f}")

print(f"\nUS${spend:.2f}")
for outcome, n in done.most_common():
    print(f"  {n:5d}  {outcome}")
