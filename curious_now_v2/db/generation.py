from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.generation import packet as packet_module
from curious_now_v2.generation import present as present_module
from curious_now_v2.generation.client import CodexGenerator, Generator
from curious_now_v2.generation.judge import declined_reason, judge_mechanism
from curious_now_v2.generation.packet import extract_packet
from curious_now_v2.generation.present import generate_presentation


def _one(cursor: psycopg.Cursor[Any]) -> tuple[Any, ...]:
    """A RETURNING clause always yields a row; make that explicit for callers."""

    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("expected a returned row")
    return cast("tuple[Any, ...]", row)


# Enough text to be worth spending inference on; the gate has already decided
# the story can support a layer.
MIN_WORDS = 150


@dataclass(frozen=True)
class GenerationRunResult:
    attempted: int
    generated: int
    declined_explain: int
    withheld_kind: int
    relabelled: int
    # Explains withdrawn by the judge for listing capabilities, not mechanism.
    judged_out: int
    invalid: int
    failed: int
    cost_usd: float


@dataclass(frozen=True)
class PendingStory:
    story_id: UUID
    item_id: UUID
    source_name: str
    content_type: str
    title: str
    text: str
    # What retrieval actually got, not what we wish it got. Explain and
    # Technical are both gated on this, and it was a hardcoded constant.
    text_sufficiency: str


def list_stories_needing_presentations(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
    regenerate: bool = False,
    story_ids: Sequence[UUID] | None = None,
) -> tuple[PendingStory, ...]:
    """Published stories awaiting presentation, grounded in their richest item.

    Stories come back in id order, which is arbitrary and therefore fair. It is
    deliberately not richest-first: ordering a limited batch by length would
    hand every slot to whichever source publishes the longest documents, which
    is how two earlier fairness faults in this pipeline worked.

    `story_ids` restricts the batch to named stories, so one result can be
    re-examined without paying for a whole batch.
    """

    # Skip what is already being shown, rather than everything that has ever
    # had a packet. A story withheld after it had published keeps that packet,
    # so excluding on the packet alone left it in draft for good — the reopening
    # that `reconsider_withheld` performs would have had no effect at all.
    having = "" if regenerate else """
        AND NOT (
          s.status = 'published'
          AND EXISTS (
            SELECT 1 FROM evidence_packets ep
            WHERE ep.story_id = s.id AND ep.status = 'valid'
          )
        )
    """
    chosen = "AND s.id = ANY(%s)" if story_ids else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT ON (s.id)
              s.id, i.id, src.name, i.content_type,
              COALESCE(dt.text, s.working_title), i.full_text,
              CASE WHEN i.full_text_kind = 'fulltext'
                   THEN 'open_full_text' ELSE COALESCE(i.access_class, 'abstract')
              END
            FROM stories s
            JOIN story_items si ON si.story_id = s.id
            JOIN items i ON i.id = si.item_id
            JOIN sources src ON src.id = i.source_id
            LEFT JOIN display_titles dt
              ON dt.id = s.current_display_title_id AND dt.status = 'valid'
            WHERE s.status <> 'hidden'
              AND s.withheld_kind IS NULL
              AND cardinality(s.supported_depths) > 0
              AND src.active
              AND i.full_text IS NOT NULL
              AND COALESCE(i.full_text_words, 0) >= %s
              {chosen}
              {having}
            ORDER BY s.id, i.full_text_words DESC
            LIMIT %s;
            """,
            (MIN_WORDS, list(story_ids), limit) if story_ids else (MIN_WORDS, limit),
        )
        return tuple(
            PendingStory(
                story_id=row[0],
                item_id=row[1],
                source_name=row[2],
                content_type=row[3],
                title=row[4],
                text=row[5],
                text_sufficiency=row[6],
            )
            for row in cursor
        )


def _withhold(
    connection: psycopg.Connection[Any],
    *,
    story_id: UUID,
    kind: str,
    claim: str,
    now: datetime,
) -> None:
    """Return a story to draft because of what it is, not what it lacks.

    A podcast series or a funding award may be perfectly well evidenced and
    still not be a development anyone can be shown an explanation of.

    The classifier version is recorded because this judgement is only as good
    as the taxonomy behind it: adding `explainer` turned a wildfire piece from
    something we dropped into one of the better things in the feed. A story
    withheld under an older version is a candidate for reconsideration, and
    without this there is no way to find one.
    """

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE stories SET
              status = 'draft',
              -- supported_depths is deliberately untouched. It records what the
              -- text can carry, which the gate computes and withholding does
              -- not change: a podcast episode we decline to explain still has
              -- whatever prose it always had. Clearing it made a reopened story
              -- invisible to the generation queue, so reconsidering a taxonomy
              -- decision silently did nothing until the gate happened to run.
              withheld_kind = %s,
              withheld_by = %s,
              publication_reasons = %s,
              gated_at = %s,
              updated_at = now()
            WHERE id = %s;
            """,
            (
                kind,
                packet_module.PROMPT_VERSION,
                Jsonb(
                    [
                        f"withheld: this is a {kind.replace('_', ' ')}, "
                        "not a development to explain",
                        claim[:200],
                        f"classified by {packet_module.PROMPT_VERSION}",
                    ]
                ),
                now,
                story_id,
            ),
        )


# A type the classifier can withdraw. Demotion only, deliberately: having read
# the text, it can say a book review is not a research paper, but nothing it
# reads can establish that a paper was peer reviewed. A claim about vetting has
# to come from the record, never from a model's impression of the prose.
NOT_RESEARCH = frozenset({"not_science", "announcement"})
PAPER_TYPES = frozenset({"peer_reviewed", "preprint"})


def reconsider_withheld(connection: psycopg.Connection[Any]) -> int:
    """Reopen stories dropped by a classifier we no longer run.

    Adding `explainer` to the taxonomy turned a piece on how a wildfire builds
    its own thunderstorm from something we discarded as not science into one of
    the better things in the corpus. Nothing would have found it again: the
    withholding was recorded and never revisited. A judgement is only as good
    as the taxonomy behind it, so a change of taxonomy reopens the question.
    """

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE stories SET
              withheld_kind = NULL,
              withheld_by = NULL,
              publication_reasons = '[]'::jsonb,
              updated_at = now()
            WHERE withheld_kind IS NOT NULL
              AND withheld_by IS DISTINCT FROM %s;
            """,
            (packet_module.PROMPT_VERSION,),
        )
        return cursor.rowcount


def _reconcile_content_type(
    connection: psycopg.Connection[Any],
    *,
    item_id: UUID,
    content_type: str,
    story_kind: str,
) -> bool:
    """Withdraw a paper label the text does not support."""

    if story_kind not in NOT_RESEARCH or content_type not in PAPER_TYPES:
        return False
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE items SET
              content_type = 'other',
              content_type_basis = 'classifier',
              content_type_note = %s,
              updated_at = now()
            WHERE id = %s AND content_type_basis <> 'classifier';
            """,
            (
                f"labelled {content_type} on arrival; the text is a "
                f"{story_kind.replace('_', ' ')}",
                item_id,
            ),
        )
        return cursor.rowcount > 0


def _store(
    connection: psycopg.Connection[Any],
    *,
    story: PendingStory,
    extracted: packet_module.ExtractedPacket,
    presentation: present_module.Presentation,
    model: str,
    now: datetime,
) -> None:
    """Persist packet, claims, spine, and presentations as one version.

    Everything written here references one packet version and one spine
    version, so a reader can never be shown a mixture of two.
    """

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(max(version), 0) + 1 FROM evidence_packets
            WHERE story_id = %s;
            """,
            (story.story_id,),
        )
        version = cast(int, _one(cursor)[0])

        cursor.execute(
            """
            INSERT INTO evidence_packets (
              story_id, version, status, text_sufficiency, central_claim,
              limitations, provenance, validated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                story.story_id,
                version,
                "valid" if presentation.valid else "invalid",
                story.text_sufficiency,
                extracted.central_claim,
                Jsonb(list(extracted.limitations)),
                Jsonb(
                    {
                        "model": model,
                        "prompt_version": packet_module.PROMPT_VERSION,
                        "story_kind": extracted.story_kind,
                        "grounding_item": str(story.item_id),
                        "prerequisites": list(extracted.prerequisites),
                    }
                ),
                now if presentation.valid else None,
            ),
        )
        packet_id = cast(UUID, _one(cursor)[0])

        for ordinal, claim in enumerate(extracted.claims):
            cursor.execute(
                """
                INSERT INTO evidence_claims (
                  evidence_packet_id, ordinal, claim_kind, claim_text, confidence
                ) VALUES (%s, %s, %s, %s, %s) RETURNING id;
                """,
                (packet_id, ordinal, claim.kind.value, claim.text, claim.confidence),
            )
            claim_id = cast(UUID, _one(cursor)[0])
            cursor.execute(
                """
                INSERT INTO claim_evidence (claim_id, item_id, support_kind, excerpt)
                VALUES (%s, %s, 'direct', %s)
                ON CONFLICT DO NOTHING;
                """,
                (claim_id, story.item_id, claim.excerpt),
            )

        cursor.execute(
            """
            INSERT INTO conceptual_spines (
              story_id, evidence_packet_id, version, status, central_claim,
              novelty, core_intuition, essential_qualification,
              prerequisite_concepts, prompt_version, model_provider, model_name,
              validated_at
            )
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 'openai', %s, %s)
            RETURNING id;
            """,
            (
                story.story_id,
                packet_id,
                "valid" if presentation.valid else "invalid",
                extracted.central_claim,
                presentation.spine_novelty,
                presentation.spine_intuition,
                presentation.spine_qualification,
                Jsonb(list(extracted.prerequisites)),
                present_module.PROMPT_VERSION,
                model,
                now if presentation.valid else None,
            ),
        )
        spine_id = cast(UUID, _one(cursor)[0])

        cursor.execute(
            """
            INSERT INTO display_titles (
              story_id, evidence_packet_id, conceptual_spine_id, version, text,
              status, prompt_version, model_provider, model_name, validated_at
            )
            VALUES (
              %s, %s, %s,
              (SELECT COALESCE(max(version), 0) + 1 FROM display_titles
               WHERE story_id = %s),
              %s, %s, %s, 'openai', %s, %s
            )
            RETURNING id;
            """,
            (
                story.story_id,
                packet_id,
                spine_id,
                story.story_id,
                presentation.display_title or story.title,
                # Judged on its own terms: a hyped or over-long title is
                # invalid as a title, and says nothing about the explanation.
                "valid" if presentation.title_valid else "invalid",
                present_module.PROMPT_VERSION,
                model,
                now if presentation.title_valid else None,
            ),
        )
        title_id = cast(UUID, _one(cursor)[0])

        # The qualification is not a field the reader is shown; it is written
        # into the Glance prose. What is kept here is the span locating it, so
        # a later audit can ask whether it survived without reading every word.
        layers: tuple[tuple[ExplanationDepth, str, bool, dict[str, str], str], ...] = (
            (
                ExplanationDepth.GLANCE,
                presentation.glance,
                presentation.glance_supported,
                {"qualification_span": presentation.glance_qualification_span}
                if presentation.glance_qualification_span
                else {},
                "",
            ),
            (
                ExplanationDepth.EXPLAIN,
                presentation.explain,
                presentation.explain_supported,
                {},
                presentation.explain_declined_reason,
            ),
        )
        for depth, body, supported, provenance, declined in layers:
            usable = supported and bool(body.strip()) and presentation.valid
            cursor.execute(
                """
                INSERT INTO explanations (
                  story_id, evidence_packet_id, conceptual_spine_id, depth,
                  status, content, plain_text, model_provider, model_name,
                  prompt_version, input_tokens, output_tokens, failure_reason,
                  validated_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, 'openai', %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT DO NOTHING;
                """,
                (
                    story.story_id,
                    packet_id,
                    spine_id,
                    depth.value,
                    "valid" if usable else ("invalid" if supported else "failed"),
                    Jsonb(provenance if supported else {}),
                    body or None,
                    model,
                    present_module.PROMPT_VERSION,
                    presentation.completion.usage.input_tokens,
                    presentation.completion.usage.output_tokens,
                    None if supported else (declined or "declined"),
                    now if usable else None,
                ),
            )

        if presentation.valid:
            # Publication happens here and only here: a story is offered to a
            # reader when there is something to show them, which is not a fact
            # the gate can know from counting words.
            #
            # The display title is pointed at separately, because a title that
            # breaks the contract falls back to the source's own headline —
            # an attributed fact rather than our editorial text — while the
            # explanation it belongs to goes out unaffected.
            cursor.execute(
                """
                UPDATE stories SET
                  status = 'published',
                  published_at = COALESCE(published_at, now()),
                  current_evidence_packet_id = %s,
                  current_display_title_id = %s,
                  updated_at = now()
                WHERE id = %s AND status <> 'hidden';
                """,
                (
                    packet_id,
                    title_id if presentation.title_valid else None,
                    story.story_id,
                ),
            )


def run_generation(
    database_url: str,
    *,
    limit: int = 10,
    model: str | None = None,
    regenerate: bool = False,
    generator: Generator | None = None,
    story_ids: Sequence[UUID] | None = None,
) -> GenerationRunResult:
    """Extract an evidence packet, then write the layers it can support."""

    engine = generator or CodexGenerator(model=model or CodexGenerator.model)
    now = datetime.now(UTC)
    generated = declined = invalid = failed = withheld = relabelled = 0
    judged_out = 0
    cost = 0.0

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('generate', 'running') RETURNING id;
                """
            )
            run_id = cast(UUID, _one(cursor)[0])

        reopened = reconsider_withheld(connection)
        if reopened:
            log = f"reopened {reopened} stories withheld by an older classifier"
            print(log)

        pending = list_stories_needing_presentations(
            connection, limit=limit, regenerate=regenerate, story_ids=story_ids
        )
        for story in pending:
            extracted = extract_packet(
                engine,
                source_name=story.source_name,
                content_type=story.content_type,
                title=story.title,
                text=story.text,
            )
            cost += extracted.completion.usage.cost(engine.model)
            if not extracted.usable:
                failed += 1
                continue

            if _reconcile_content_type(
                connection,
                item_id=story.item_id,
                content_type=story.content_type,
                story_kind=extracted.story_kind,
            ):
                relabelled += 1

            if not extracted.worth_publishing:
                # An announcement reports that something happened; the feed is
                # for what was found or built. Withdraw it rather than spend a
                # second call explaining the mechanism of a podcast.
                _withhold(
                    connection,
                    story_id=story.story_id,
                    kind=extracted.story_kind,
                    claim=extracted.central_claim,
                    now=now,
                )
                withheld += 1
                continue

            presentation = generate_presentation(
                engine,
                extracted,
                source_name=story.source_name,
                content_type=story.content_type,
                text=story.text,
            )
            cost += presentation.completion.usage.cost(engine.model)
            if not presentation.completion.ok:
                failed += 1
                continue

            if presentation.explain_supported and presentation.explain.strip():
                # A third call, and the cheapest of the three: it reads the
                # Explain alone, not the source. The writer decides whether the
                # evidence carries a mechanism and, asked to write, tends to
                # find that it does.
                judgement = judge_mechanism(
                    engine,
                    title=presentation.display_title or story.title,
                    source_name=story.source_name,
                    explain=presentation.explain,
                )
                cost += judgement.completion.usage.cost(engine.model)
                if not judgement.explains:
                    presentation = present_module.Presentation(
                        **{
                            **presentation.__dict__,
                            "explain": "",
                            "explain_supported": False,
                            "explain_declined_reason": declined_reason(judgement),
                        }
                    )
                    judged_out += 1

            _store(
                connection,
                story=story,
                extracted=extracted,
                presentation=presentation,
                model=engine.model,
                now=now,
            )
            if presentation.valid:
                generated += 1
                if not presentation.explain_supported:
                    declined += 1
            else:
                invalid += 1

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                  status = %s, finished_at = now(), counters = %s
                WHERE id = %s;
                """,
                (
                    "succeeded" if generated else "partial",
                    Jsonb(
                        {
                            "attempted": len(pending),
                            "generated": generated,
                            "declined_explain": declined,
                            "withheld_kind": withheld,
                            "reopened": reopened,
                            "relabelled": relabelled,
                            "judged_out": judged_out,
                            "invalid": invalid,
                            "failed": failed,
                            "cost_usd": round(cost, 4),
                        }
                    ),
                    run_id,
                ),
            )

    return GenerationRunResult(
        attempted=len(pending),
        generated=generated,
        declined_explain=declined,
        withheld_kind=withheld,
        relabelled=relabelled,
        judged_out=judged_out,
        invalid=invalid,
        failed=failed,
        cost_usd=round(cost, 4),
    )
