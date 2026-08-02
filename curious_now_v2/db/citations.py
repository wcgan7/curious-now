"""Writing typed citation edges, and the stub papers they point at.

An edge needs a paper at both ends, and the far end is almost never a paper we
hold: a reference is a work we know exists because someone we read depends on
it. So this creates stubs — a title, an identifier, and nothing else — which is
the concrete form of the decision to accrete the graph around what we actually
cover rather than mirror a bibliographic database wholesale.

A stub is deliberately thin. It carries no abstract, no text, and an
access_class of metadata_only, and it exists so an edge has somewhere to point
and so the ingestion queue can rank what to fetch next. When the paper itself is
later retrieved, the same row is filled in rather than duplicated, because the
identifier is unique.

Only references carrying a DOI or an arXiv id become stubs. A citation string
alone cannot be deduplicated -- the same paper is cited a dozen ways across a
corpus -- and inventing a node per spelling would produce exactly the useless
graph that the concept design was written to avoid.
"""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.generation.citations import CitedWork, TypedEdge

# Bibliography entries run "Authors. Title. Venue, year." Splitting on the full
# stops gives the pieces, and the title is the first that is neither an author
# list nor a venue. Position cannot decide it: "Vaswani, A." and "et al." are
# two pieces in one style and one in another, so counting from the front lands
# on the venue as often as the title.
_SPLIT = re.compile(r"\.\s+")
# "Smith, J", "Aitken, S. J", "Kunegis, J.; Schmidt, S".
_AUTHORS = re.compile(r"^[A-Z][A-Za-z'’\-]+,\s*[A-Z]|^et al\b", re.I)
_VENUE_LEAD = re.compile(
    r"^(in|proceedings|advances|arxiv|pages|volume|vol\.|pp\.|doi|https?:)",
    re.I,
)
# A venue names its year; a title almost never does.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_MIN_TITLE_CHARS = 12
MAX_TITLE_CHARS = 300


@dataclass(frozen=True)
class EdgeWriteResult:
    written: int = 0
    stubs_created: int = 0
    skipped: tuple[str, ...] = field(default_factory=tuple)


def guess_title(citation_text: str) -> str:
    """The best title available from a citation string.

    Never confident, and recorded as such: metadata.title_source says where it
    came from so a later retrieval can replace it without wondering whether the
    stored title was authoritative.
    """

    parts = [
        part.strip()
        for part in _SPLIT.split(citation_text)
        if len(part.strip()) >= _MIN_TITLE_CHARS
    ]
    for part in parts:
        if _AUTHORS.match(part) or _VENUE_LEAD.match(part) or _YEAR.search(part):
            continue
        return part[:MAX_TITLE_CHARS]
    if parts:
        return max(parts, key=len)[:MAX_TITLE_CHARS]
    return citation_text.strip()[:MAX_TITLE_CHARS] or "untitled reference"


def list_cited_works(
    connection: psycopg.Connection[Any], item_id: UUID
) -> list[CitedWork]:
    """An item's stored bibliography, in the shape the typing pass reads."""

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT ref_key, label, citation_text, doi, arxiv_id, mentions,
                      cited_sections, contexts
               FROM item_references WHERE item_id = %s
               ORDER BY mentions DESC, ref_key;""",
            (item_id,),
        )
        return [
            CitedWork(
                ref_key=row[0],
                label=row[1],
                citation_text=row[2],
                doi=row[3],
                arxiv_id=row[4],
                mentions=row[5],
                cited_sections=tuple(row[6] or ()),
                contexts=tuple(
                    sentence
                    for entry in (row[7] or [])
                    if (sentence := (entry or {}).get("sentence"))
                ),
            )
            for row in cursor.fetchall()
        ]


def list_items_to_type(
    connection: psycopg.Connection[Any], *, limit: int, retype: bool = False
) -> list[tuple[UUID, str]]:
    """Papers whose bibliography is worth a typing pass.

    Requires an in-text citation and a paper of its own: without the first there
    is no sentence to ground a relation, and without the second there is nothing
    for an edge to start from.
    """

    clause = (
        ""
        if retype
        else "AND NOT EXISTS (SELECT 1 FROM paper_relations pr "
        "WHERE pr.evidence_item_id = i.id)"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT i.id, i.title
            FROM items i
            JOIN item_papers ip ON ip.item_id = i.id
            WHERE EXISTS (
                    SELECT 1 FROM item_references r
                    WHERE r.item_id = i.id AND r.mentions > 0
                  )
              {clause}
            GROUP BY i.id, i.title
            ORDER BY count(*) DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [(row[0], row[1] or "") for row in cursor.fetchall()]


def _citing_paper(cursor: psycopg.Cursor[Any], item_id: UUID) -> UUID | None:
    cursor.execute(
        """SELECT paper_id FROM item_papers WHERE item_id = %s
           ORDER BY match_confidence DESC LIMIT 1;""",
        (item_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def find_or_create_paper(
    cursor: psycopg.Cursor[Any], work: CitedWork
) -> tuple[UUID | None, bool]:
    """The paper this reference denotes, creating a stub if we have none.

    Returns (id, created). The identifier is matched case-insensitively because
    that is how the unique indexes are built, and DOIs are routinely cited in
    mixed case.
    """

    for column, value in (("doi", work.doi), ("arxiv_id", work.arxiv_id)):
        if not value:
            continue
        cursor.execute(
            f"SELECT id FROM papers WHERE lower({column}) = lower(%s) LIMIT 1;",
            (value,),
        )
        found = cursor.fetchone()
        if found:
            return found[0], False

    if not (work.doi or work.arxiv_id):
        return None, False

    cursor.execute(
        """
        INSERT INTO papers (title, doi, arxiv_id, access_class, metadata)
        VALUES (%s, %s, %s, 'metadata_only', %s)
        ON CONFLICT DO NOTHING
        RETURNING id;
        """,
        (
            guess_title(work.citation_text),
            work.doi,
            work.arxiv_id,
            Jsonb(
                {
                    "origin": "citation_stub",
                    "title_source": "citation_string",
                    "citation_text": work.citation_text[:1000],
                }
            ),
        ),
    )
    inserted = cursor.fetchone()
    if inserted:
        return inserted[0], True

    # Another writer created it between the select and the insert.
    for column, value in (("doi", work.doi), ("arxiv_id", work.arxiv_id)):
        if not value:
            continue
        cursor.execute(
            f"SELECT id FROM papers WHERE lower({column}) = lower(%s) LIMIT 1;",
            (value,),
        )
        found = cursor.fetchone()
        if found:
            return found[0], False
    return None, False


def store_typed_edges(
    connection: psycopg.Connection[Any],
    *,
    item_id: UUID,
    edges: tuple[TypedEdge, ...],
    works: list[CitedWork],
    prompt_version: str,
) -> EdgeWriteResult:
    """Write one paper's typed citations, creating stubs for their targets.

    Every edge carries the sentence that established it. That quote is the whole
    warrant for the claim: it is what makes "A extends B" checkable rather than
    asserted, and what will later let the claim be tested against B once B has
    been read too.
    """

    by_key = {work.ref_key: work for work in works}
    written = 0
    stubs = 0
    skipped: list[str] = []

    with connection.transaction(), connection.cursor() as cursor:
        citing = _citing_paper(cursor, item_id)
        if citing is None:
            # Journalism, and papers whose own identifier was never resolved.
            return EdgeWriteResult(skipped=("citing item has no paper record",))

        for edge in edges:
            work = by_key.get(edge.ref_key)
            if work is None:
                skipped.append(f"{edge.ref_key}: no such reference")
                continue

            target, created = find_or_create_paper(cursor, work)
            if target is None:
                skipped.append(f"{edge.ref_key}: no identifier to key a paper on")
                continue
            stubs += int(created)
            if target == citing:
                # A paper citing its own preprint. The table forbids it, and it
                # is not an edge anyone would want to traverse.
                skipped.append(f"{edge.ref_key}: cites itself")
                continue

            cursor.execute(
                """
                INSERT INTO paper_relations (
                  from_paper_id, to_paper_id, relation, source,
                  evidence_item_id, provenance
                ) VALUES (%s, %s, %s, 'paper_text', %s, %s)
                ON CONFLICT (from_paper_id, to_paper_id, relation)
                DO UPDATE SET
                  evidence_item_id = EXCLUDED.evidence_item_id,
                  provenance = EXCLUDED.provenance;
                """,
                (
                    citing,
                    target,
                    edge.relation,
                    item_id,
                    Jsonb(
                        {
                            "quote": edge.quote,
                            "reason": edge.reason,
                            "ref_key": edge.ref_key,
                            "mentions": work.mentions,
                            "cited_sections": list(work.cited_sections),
                            "prompt_version": prompt_version,
                        }
                    ),
                ),
            )
            written += 1

    return EdgeWriteResult(written=written, stubs_created=stubs, skipped=tuple(skipped))


@dataclass(frozen=True)
class TypingRunResult:
    attempted: int = 0
    typed: int = 0
    edges: int = 0
    stubs: int = 0
    failed: int = 0
    cost: float = 0.0
    # Edges the model found and evidenced but that could not be written. The
    # first full run discarded these, which left the question of whether paying
    # an index to resolve the remaining references would buy anything
    # unanswerable except by guessing.
    skipped: Counter[str] = field(default_factory=Counter)

    @property
    def blocked_by_identifier(self) -> int:
        """Typed edges lost only because their target could not be keyed."""

        return sum(
            count
            for reason, count in self.skipped.items()
            if "no identifier" in reason
        )


def run_citation_typing(
    database_url: str,
    *,
    limit: int = 10,
    retype: bool = False,
    generator: Any = None,
    workers: int = 1,
    progress_every: int = 25,
) -> TypingRunResult:
    """Type the citations of papers whose bibliography we hold.

    One model call per paper. The call is the expensive part and the writes are
    trivial, so failures are isolated per paper: a paper whose reply cannot be
    validated leaves the others alone rather than aborting the run.
    """

    from curious_now_v2.generation.citations import (
        PROMPT_VERSION,
        type_citations,
    )
    from curious_now_v2.generation.client import CodexGenerator

    writer = generator if generator is not None else CodexGenerator()

    with psycopg.connect(database_url) as connection:
        targets = list_items_to_type(connection, limit=limit, retype=retype)

    def one(target: tuple[UUID, str]) -> tuple[EdgeWriteResult | None, float]:
        """Type and store a single paper, on its own connection.

        Each worker opens its own: psycopg connections are not shared between
        threads, and a paper that fails must not roll back another's edges.
        """

        item_id, title = target
        with psycopg.connect(database_url) as connection:
            works = list_cited_works(connection, item_id)
            result = type_citations(writer, title=title, works=works)
            spent = result.completion.usage.cost(getattr(writer, "model", ""))
            if not result.completion.ok:
                return None, spent
            written = store_typed_edges(
                connection,
                item_id=item_id,
                edges=result.edges,
                works=works,
                prompt_version=PROMPT_VERSION,
            )
            connection.commit()
        return written, spent

    attempted = typed = edges = stubs = failed = 0
    cost = 0.0
    skipped: Counter[str] = Counter()

    # Almost all of a call's duration is spent waiting on the model, so threads
    # buy close to a linear speed-up here.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(one, target): target for target in targets}
        for future in as_completed(futures):
            attempted += 1
            try:
                written, spent = future.result()
            except Exception as error:  # noqa: BLE001
                # One paper's failure is not the run's.
                failed += 1
                print(f"  failed: {type(error).__name__}: {error}")  # noqa: T201
                continue
            cost += spent
            if written is None:
                failed += 1
                continue
            if written.written:
                typed += 1
            edges += written.written
            stubs += written.stubs_created
            for reason in written.skipped:
                # Reasons arrive prefixed with the reference key, which is
                # unique per paper and would make every count one.
                _, _, tail = reason.partition(": ")
                skipped[tail or reason] += 1
            if progress_every and attempted % progress_every == 0:
                print(  # noqa: T201
                    f"  {attempted}/{len(targets)} typed, {edges} edges, "
                    f"{stubs} stubs, ${cost:.2f}"
                )

    return TypingRunResult(attempted, typed, edges, stubs, failed, cost, skipped)


@dataclass(frozen=True)
class LookupRunResult:
    attempted: int = 0
    resolved: int = 0
    declined: int = 0
    rows_updated: int = 0


def run_reference_lookup(
    database_url: str,
    *,
    limit: int = 500,
    opener: Any = None,
    progress_every: int = 100,
) -> LookupRunResult:
    """Recover identifiers for references cited without one.

    Works on DISTINCT citation strings, not rows: the same paper is cited by
    several of ours, and one lookup should serve all of them.

    Only references the body actually cited are attempted. An entry no sentence
    points at cannot carry a typed edge, so resolving it buys nothing that would
    justify the request.
    """

    from curious_now_v2.retrieval import reference_lookup

    attempted = resolved = declined = rows = 0

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT citation_text, count(*) AS rows, sum(mentions) AS mentions
                FROM item_references
                WHERE doi IS NULL AND arxiv_id IS NULL AND mentions > 0
                  AND length(citation_text) > 40
                GROUP BY citation_text
                ORDER BY mentions DESC, rows DESC
                LIMIT %s;
                """,
                (limit,),
            )
            targets = cursor.fetchall()

        last = 0.0
        for index, (citation_text, _rows, _mentions) in enumerate(targets, start=1):
            attempted += 1
            last = reference_lookup.pace(last)
            try:
                match = reference_lookup.resolve(
                    citation_text,
                    **({"opener": opener} if opener is not None else {}),
                )
            except reference_lookup.LookupUnavailable as error:
                # Continuing would record every remaining reference as
                # unmatchable, which is a claim about the corpus rather than
                # about the index being unavailable.
                print(f"  lookup unavailable, stopping: {error}")  # noqa: T201
                break
            if match is None:
                declined += 1
            else:
                resolved += 1
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE item_references
                           SET doi = COALESCE(doi, %s),
                               arxiv_id = COALESCE(arxiv_id, %s),
                               identifier_source = 'crossref_bibliographic',
                               identifier_confidence = %s
                         WHERE citation_text = %s
                           AND doi IS NULL AND arxiv_id IS NULL;
                        """,
                        (match.doi, match.arxiv_id, match.confidence, citation_text),
                    )
                    rows += cursor.rowcount
                connection.commit()

            if progress_every and index % progress_every == 0:
                print(  # noqa: T201
                    f"  {index}/{len(targets)} looked up, "
                    f"{resolved} resolved, {rows} rows updated"
                )

    return LookupRunResult(attempted, resolved, declined, rows)
