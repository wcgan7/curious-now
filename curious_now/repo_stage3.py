from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from curious_now.api.schemas import GlossaryEntry, GlossaryLookupResponse


def glossary_lookup(conn: psycopg.Connection[Any], *, term: str) -> GlossaryLookupResponse:
    q = term.strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id AS glossary_entry_id, term, definition_short, definition_long
            FROM glossary_entries
            WHERE lower(term) = lower(%s)
               OR aliases ? %s
            LIMIT 1;
            """,
            (q, q),
        )
        row = cur.fetchone()
    if not row:
        raise KeyError("not found")
    return GlossaryLookupResponse(
        entry=GlossaryEntry(
            glossary_entry_id=row["glossary_entry_id"],
            term=row["term"],
            definition_short=row["definition_short"],
            definition_long=row["definition_long"],
        )
    )


def glossary_entries_for_cluster(
    conn: psycopg.Connection[Any], *, cluster_id: UUID
) -> list[GlossaryEntry]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id AS glossary_entry_id, g.term, g.definition_short, g.definition_long
            FROM cluster_glossary_links l
            JOIN glossary_entries g ON g.id = l.glossary_entry_id
            WHERE l.cluster_id = %s
            ORDER BY l.score DESC, g.term ASC
            LIMIT 25;
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()
    return [
        GlossaryEntry(
            glossary_entry_id=r["glossary_entry_id"],
            term=r["term"],
            definition_short=r["definition_short"],
            definition_long=r["definition_long"],
        )
        for r in rows
    ]
