from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.db import ranking as ranking_module
from curious_now_v2.generation import direct as direct_module
from curious_now_v2.generation import packet as packet_module
from curious_now_v2.generation import significance as significance_module
from curious_now_v2.generation.client import CodexGenerator, Generator, Usage
from curious_now_v2.generation.direct import generate_layer, planned_depths
from curious_now_v2.generation.packet import extract_packet
from curious_now_v2.pipeline import scoring


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
    explain_ineligible: int
    explain_failed: int
    withheld_kind: int
    relabelled: int
    technical: int
    technical_failed: int
    titles_generated: int
    title_failed: int
    failed: int
    cost_usd: float

    @property
    def without_explain(self) -> int:
        """Compatibility name for intentionally Idea-only stories."""

        return self.explain_ineligible


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
    is_primary_material: bool
    # Scheduler composition follows the same evidence shape as the reader:
    # reported/news-like material has a protected lane, while primary papers
    # remain the majority.  Keep this on the selected grounding item rather
    # than inferring it later from a source name.
    is_accessible_material: bool
    published_at: datetime


def list_stories_needing_presentations(
    connection: psycopg.Connection[Any],
    *,
    limit: int,
    regenerate: bool = False,
    story_ids: Sequence[UUID] | None = None,
    source: str | None = None,
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
    from_source = "" if source is None else """
        AND EXISTS (
          SELECT 1
          FROM story_items source_si
          JOIN items source_i ON source_i.id = source_si.item_id
          JOIN sources source_src ON source_src.id = source_i.source_id
          WHERE source_si.story_id = s.id AND source_src.name = %s
        )
    """
    parameters: list[object] = [MIN_WORDS]
    if source is not None:
        parameters.append(source)
    if story_ids:
        parameters.append(list(story_ids))
    parameters.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT ON (s.id)
              s.id, i.id, src.name, i.content_type,
              i.title, i.full_text,
              CASE i.full_text_kind
                   WHEN 'fulltext' THEN 'open_full_text'
                   WHEN 'abstract' THEN 'abstract'
                   ELSE COALESCE(i.access_class, 'metadata_only')
              END,
              i.content_type IN ('preprint', 'peer_reviewed', 'report', 'dataset')
                OR src.role = 'primary_research',
              src.role = 'journalism'
                OR i.content_type IN ('news', 'press_release', 'blog'),
              COALESCE(i.published_at, s.last_evidence_at, s.created_at)
            FROM stories s
            JOIN story_items si ON si.story_id = s.id
            JOIN items i ON i.id = si.item_id
            JOIN sources src ON src.id = i.source_id
            WHERE s.status <> 'hidden'
              AND s.withheld_kind IS NULL
              AND cardinality(s.supported_depths) > 0
              AND src.active
              AND i.full_text_status <> 'blocked'
              AND i.full_text IS NOT NULL
              AND COALESCE(i.full_text_words, 0) >= %s
              AND CASE i.full_text_kind
                       WHEN 'fulltext' THEN 'open_full_text'
                       WHEN 'abstract' THEN 'abstract'
                       ELSE COALESCE(i.access_class, 'metadata_only')
                  END IN ('abstract', 'open_full_text')
              {from_source}
              {chosen}
              {having}
            ORDER BY s.id,
              (
                (i.content_type IN ('preprint', 'peer_reviewed', 'report', 'dataset')
                  OR src.role = 'primary_research')
                AND CASE i.full_text_kind
                         WHEN 'fulltext' THEN 'open_full_text'
                         WHEN 'abstract' THEN 'abstract'
                         ELSE COALESCE(i.access_class, 'metadata_only')
                    END = 'open_full_text'
              ) DESC,
              i.full_text_words DESC
            LIMIT %s;
            """,
            tuple(parameters),
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
                is_primary_material=bool(row[7]),
                is_accessible_material=bool(row[8]),
                published_at=row[9],
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


def reconsider_withheld(
    connection: psycopg.Connection[Any],
    *,
    source: str | None = None,
) -> int:
    """Reopen stories dropped by a classifier we no longer run.

    Adding `explainer` to the taxonomy turned a piece on how a wildfire builds
    its own thunderstorm from something we discarded as not science into one of
    the better things in the corpus. Nothing would have found it again: the
    withholding was recorded and never revisited. A judgement is only as good
    as the taxonomy behind it, so a change of taxonomy reopens the question.
    """

    query = """
            UPDATE stories SET
              withheld_kind = NULL,
              withheld_by = NULL,
              publication_reasons = '[]'::jsonb,
              updated_at = now()
            WHERE withheld_kind IS NOT NULL
              AND withheld_by IS DISTINCT FROM %s
    """
    parameters: list[object] = [packet_module.PROMPT_VERSION]
    if source is not None:
        query += """
          AND EXISTS (
            SELECT 1
            FROM story_items source_si
            JOIN items source_i ON source_i.id = source_si.item_id
            JOIN sources source_src ON source_src.id = source_i.source_id
            WHERE source_si.story_id = stories.id AND source_src.name = %s
          )
        """
        parameters.append(source)
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(query, tuple(parameters))
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


@dataclass(frozen=True)
class _StoredLayer:
    depth: ExplanationDepth
    body: str
    supported: bool
    content: dict[str, Any]
    declined_reason: str
    prompt_version: str
    usage: Usage


def _layers_to_store(
    layers: Sequence[direct_module.DirectLayer],
) -> tuple[_StoredLayer, ...]:
    """Adapt independent prose calls to the existing explanation rows."""

    return tuple(
        _StoredLayer(
            depth=layer.depth,
            body=layer.text,
            supported=layer.valid,
            content=layer.content,
            declined_reason=layer.completion.error or "empty output",
            prompt_version=layer.prompt_version,
            usage=layer.completion.usage,
        )
        for layer in layers
    )


def _replacement_complete(layers: Sequence[_StoredLayer]) -> bool:
    """Whether this attempt is safe to make reader-current."""

    idea_valid = any(
        layer.depth is ExplanationDepth.GLANCE and layer.supported
        for layer in layers
    )
    return idea_valid and all(
        layer.supported and bool(layer.body.strip()) for layer in layers
    )


def _can_make_current(
    layers: Sequence[_StoredLayer], *, has_current: bool
) -> bool:
    """Publish an initial Idea, but never downgrade an existing presentation."""

    idea_valid = any(
        layer.depth is ExplanationDepth.GLANCE and layer.supported
        for layer in layers
    )
    return idea_valid and (not has_current or _replacement_complete(layers))


def _store(
    connection: psycopg.Connection[Any],
    *,
    story: PendingStory,
    extracted: packet_module.ExtractedPacket,
    layers: Sequence[direct_module.DirectLayer],
    display_title: direct_module.DirectTitle | None,
    significance: str,
    model: str,
    now: datetime,
) -> bool:
    """Persist packet and independently generated reader layers as one version.

    The legacy spine row remains as a batch identifier for schema compatibility;
    it no longer plans or constrains the three pieces of prose.
    """

    stored_layers = _layers_to_store(layers)
    idea_valid = any(
        layer.depth is ExplanationDepth.GLANCE and layer.supported
        for layer in stored_layers
    )

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_evidence_packet_id FROM stories WHERE id = %s;",
            (story.story_id,),
        )
        has_current = _one(cursor)[0] is not None
        make_current = _can_make_current(stored_layers, has_current=has_current)

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
                "valid",
                story.text_sufficiency,
                extracted.central_claim,
                Jsonb(list(extracted.limitations)),
                Jsonb(
                    {
                        "model": model,
                        "prompt_version": packet_module.PROMPT_VERSION,
                        "story_kind": extracted.story_kind,
                        "field": extracted.field,
                        "grounding_item": str(story.item_id),
                        "prerequisites": list(extracted.prerequisites),
                    }
                ),
                now,
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
                "valid" if idea_valid else "invalid",
                extracted.central_claim,
                None,
                None,
                None,
                Jsonb(list(extracted.prerequisites)),
                direct_module.IDEA_PROMPT_VERSION,
                model,
                now if idea_valid else None,
            ),
        )
        spine_id = cast(UUID, _one(cursor)[0])

        title_id: UUID | None = None
        if display_title is not None and display_title.valid:
            cursor.execute(
                """
                SELECT COALESCE(max(version), 0) + 1
                FROM display_titles WHERE story_id = %s;
                """,
                (story.story_id,),
            )
            title_version = cast(int, _one(cursor)[0])
            cursor.execute(
                """
                INSERT INTO display_titles (
                  story_id, evidence_packet_id, conceptual_spine_id, version,
                  text, status, prompt_version, model_provider, model_name,
                  validated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'valid', %s, 'openai', %s, %s)
                RETURNING id;
                """,
                (
                    story.story_id,
                    packet_id,
                    spine_id,
                    title_version,
                    display_title.text,
                    display_title.prompt_version,
                    model,
                    now,
                ),
            )
            title_id = cast(UUID, _one(cursor)[0])

        for layer in stored_layers:
            usable = layer.supported and bool(layer.body.strip())
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
                    layer.depth.value,
                    "valid"
                    if usable
                    else ("invalid" if layer.supported else "failed"),
                    Jsonb(layer.content if layer.supported else {}),
                    layer.body or None,
                    model,
                    layer.prompt_version,
                    layer.usage.input_tokens,
                    layer.usage.output_tokens,
                    None
                    if layer.supported
                    else (layer.declined_reason or "declined"),
                    now if usable else None,
                ),
            )

        if make_current:
            # Publication happens here and only here: a story is offered to a
            # reader when there is something to show them, which is not a fact
            # the gate can know from counting words.
            #
            # The sort key is written here too, and only here. It is
            # time-invariant by construction, so publication is both the first
            # moment it can be computed — depth completion is known only now — and
            # the last moment it needs to be.
            cursor.execute(
                """
                SELECT
                  COALESCE(d.published_at, s.created_at),
                  COALESCE(d.source_name, %s)
                FROM stories s
                LEFT JOIN LATERAL (
                  SELECT i.published_at, src.name AS source_name
                  FROM story_items si
                  JOIN items i ON i.id = si.item_id
                  JOIN sources src ON src.id = i.source_id
                  WHERE si.story_id = s.id AND i.published_at IS NOT NULL
                  ORDER BY i.published_at DESC, src.name
                  LIMIT 1
                ) d ON TRUE
                WHERE s.id = %s;
                """,
                (story.source_name, story.story_id),
            )
            published_at, ranking_source = _one(cursor)
            density_identity = ranking_module.density_identity(
                source_name=str(ranking_source),
                field=extracted.field,
                published_at=published_at,
            )
            density_position = ranking_module.reserve_density_position(
                cursor,
                story_id=story.story_id,
                identity=density_identity,
            )
            scored = scoring.score_story(
                published_at=published_at,
                rungs_earned=scoring.completion_rungs(
                    valid_depths=sum(layer.supported for layer in stored_layers),
                    eligible_depths=len(stored_layers),
                ),
                significance=significance,
                density_position=density_position,
            )
            cursor.execute(
                """
                UPDATE stories SET
                  status = 'published',
                  published_at = COALESCE(published_at, now()),
                  current_evidence_packet_id = %s,
                  current_display_title_id = COALESCE(%s, current_display_title_id),
                  supported_depths = %s,
                  quality_score = %s,
                  significance = %s,
                  field = %s,
                  effective_at = %s,
                  ranking_reasons = %s,
                  ranked_at = now(),
                  updated_at = now()
                WHERE id = %s AND status <> 'hidden';
                """,
                (
                    packet_id,
                    title_id,
                    [layer.depth.value for layer in stored_layers],
                    scored.quality,
                    significance,
                    extracted.field,
                    scored.effective_at,
                    # Same shape run_ranking writes, so a row means the
                    # same thing whichever writer last touched it.
                    Jsonb(
                        ranking_module.ranking_payload(
                            scored,
                            identity=density_identity,
                            density_position=density_position,
                        )
                    ),
                    story.story_id,
                ),
            )

    return make_current




@dataclass
class _Outcome:
    """What one story cost, and what became of it."""

    cost: float = 0.0
    generated: int = 0
    explain_ineligible: int = 0
    explain_failed: int = 0
    withheld: int = 0
    relabelled: int = 0
    technical: int = 0
    technical_failed: int = 0
    titles_generated: int = 0
    title_failed: int = 0
    failed: int = 0
    # Why it failed. A bare count says a story did not make it and nothing
    # about whether the model refused, the call timed out, or the text was
    # unusable — which is the difference between retrying and fixing.
    reason: str = ""


def _present_one(
    connection: psycopg.Connection[Any],
    *,
    engine: Generator,
    writer: Generator,
    story: PendingStory,
    now: datetime,
) -> _Outcome:
    """Take one story from stored evidence to stored presentation.

    Separated from the run loop so that a failure has somewhere to stop. Every
    write inside is committed as it happens, so a story that raises leaves the
    corpus consistent and is simply picked up by the next run.
    """

    out = _Outcome()
    extracted = extract_packet(
        engine,
        source_name=story.source_name,
        content_type=story.content_type,
        title=story.title,
        text=story.text,
    )
    out.cost += extracted.completion.usage.cost(engine.model)
    if not extracted.usable:
        out.failed = 1
        out.reason = (
            f"packet: {extracted.completion.error}"
            if extracted.completion.error
            else "packet: no usable claims extracted"
        )
        return out

    relabelled = _reconcile_content_type(
        connection,
        item_id=story.item_id,
        content_type=story.content_type,
        story_kind=extracted.story_kind,
    )
    if relabelled:
        out.relabelled = 1

    if not extracted.worth_publishing:
        # An announcement reports that something happened; the feed is for what
        # was found or built. Withdraw it rather than spend a second call
        # explaining the mechanism of a podcast.
        _withhold(
            connection,
            story_id=story.story_id,
            kind=extracted.story_kind,
            claim=extracted.central_claim,
            now=now,
        )
        out.withheld = 1
        return out

    has_method = any(claim.kind.value == "method" for claim in extracted.claims)
    content_type = "other" if relabelled else story.content_type
    depths = planned_depths(
        is_primary_material=story.is_primary_material and not relabelled,
        text_sufficiency=story.text_sufficiency,
        has_method=has_method,
    )
    if not depths:
        # The queue excludes metadata and snippets. Keep this guard close to
        # inference as well, so a directly requested stale story is not spent.
        out.failed = 1
        out.reason = "source is metadata or a snippet, not an article"
        return out

    layers = tuple(
        generate_layer(
            writer,
            depth=depth,
            content_type=content_type,
            title=story.title,
            full_text=story.text,
        )
        for depth in depths
    )
    for layer in layers:
        out.cost += layer.completion.usage.cost(writer.model)

    idea = next(
        layer for layer in layers if layer.depth is ExplanationDepth.GLANCE
    )
    explain = next(
        (layer for layer in layers if layer.depth is ExplanationDepth.EXPLAIN),
        None,
    )
    technical = next(
        (layer for layer in layers if layer.depth is ExplanationDepth.TECHNICAL),
        None,
    )
    layer_errors: list[str] = []
    if explain is None:
        out.explain_ineligible = 1
    elif not explain.valid:
        out.explain_failed = 1
        layer_errors.append(
            f"explain: {explain.completion.error or 'empty output'}"
        )
    if technical is not None:
        if technical.valid:
            out.technical = 1
        else:
            out.technical_failed = 1
            layer_errors.append(
                f"technical: {technical.completion.error or 'empty output'}"
            )

    if not idea.valid:
        layer_errors.insert(0, f"idea: {idea.completion.error or 'empty output'}")

    display_title: direct_module.DirectTitle | None = None
    if idea.valid and direct_module.should_generate_title(content_type):
        display_title = direct_module.generate_title(
            writer,
            source_title=story.title,
            idea=idea.text,
        )
        out.cost += display_title.completion.usage.cost(writer.model)
        if display_title.valid:
            out.titles_generated = 1
        else:
            # The source title remains the safe fallback. A transient title
            # failure must not withhold an otherwise complete explanation.
            out.title_failed = 1

    # Whether the result would change what someone in the field does next. Its
    # own call rather than a question bolted onto one of the writing prompts.
    verdict = (
        significance_module.judge_significance(
            engine,
            title=story.title,
            source_name=story.source_name,
            claims=[
                significance_module.CandidateClaim(
                    claim_kind=claim.kind.value,
                    claim_text=claim.text,
                    excerpt=claim.excerpt,
                )
                for claim in extracted.claims
            ],
        )
        if idea.valid
        else None
    )
    if verdict is not None:
        out.cost += verdict.completion.usage.cost(engine.model)

    committed = _store(
        connection,
        story=story,
        extracted=extracted,
        layers=layers,
        display_title=display_title,
        significance=verdict.verdict if verdict is not None else "unclear",
        model=writer.model,
        now=now,
    )
    if committed:
        out.generated = 1
        if layer_errors:
            out.reason = "; ".join(layer_errors)
    else:
        out.failed = 1
        out.reason = "; ".join(layer_errors) or "eligible depth was not generated"
    return out


def run_generation(
    database_url: str,
    *,
    limit: int = 10,
    model: str | None = None,
    regenerate: bool = False,
    generator: Generator | None = None,
    story_ids: Sequence[UUID] | None = None,
    source: str | None = None,
    workers: int = 1,
) -> GenerationRunResult:
    """Extract an evidence packet, then write the layers it can support.

    `workers` runs that many stories at once. The work is a subprocess waiting
    on a model, so threads spend their time blocked rather than computing, and
    a run of nine hundred stories takes days in sequence against hours in
    parallel. Nothing about a story depends on another: each one already writes
    in its own transactions, which is what makes this safe rather than merely
    faster.

    Every worker opens its own connection. A psycopg connection is not for
    sharing between threads, and the cost of opening one is nothing beside the
    minute or more each story spends waiting on a model.
    """

    engine = generator or CodexGenerator(model=model or CodexGenerator.model)
    # The three prompts were evaluated with Luna at low effort. Packet
    # extraction and significance keep their existing effort; only the prose
    # path uses the tested setting. A supplied generator remains fully under
    # its caller's control.
    writer: Generator = (
        engine
        if generator is not None
        else CodexGenerator(model=engine.model, effort="low")
    )
    now = datetime.now(UTC)
    totals = _Outcome()
    errors: list[str] = []

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (job_name, status)
                VALUES ('generate', 'running') RETURNING id;
                """
            )
            run_id = cast(UUID, _one(cursor)[0])

        # Reconsidering an old taxonomy is corpus maintenance, not a property
        # of presenting one requested story. Applying it before the ID filter
        # made a surgical run mutate hundreds of unrelated rows.
        reopened = (
            reconsider_withheld(connection, source=source)
            if story_ids is None
            else 0
        )
        if reopened:
            print(  # noqa: T201
                f"reopened {reopened} stories withheld by an older classifier"
            )

        pending = list_stories_needing_presentations(
            connection,
            limit=limit,
            regenerate=regenerate,
            story_ids=story_ids,
            source=source,
        )
        def present(story: PendingStory) -> tuple[PendingStory, _Outcome | Exception]:
            try:
                with psycopg.connect(database_url, autocommit=True) as own:
                    return story, _present_one(
                        own, engine=engine, writer=writer, story=story, now=now
                    )
            except Exception as error:  # noqa: BLE001 — one story cannot end a run
                # Hours of subprocess calls should not be lost, along with every
                # counter, because one story raised. It stays unpresented and is
                # picked up next run.
                return story, error

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(present, story) for story in pending]
            for future in as_completed(futures):
                story, outcome = future.result()
                done += 1
                if isinstance(outcome, Exception):
                    totals.failed += 1
                    errors.append(
                        f"{story.story_id}: {type(outcome).__name__}: {outcome}"
                    )
                    continue

                totals.cost += outcome.cost
                totals.generated += outcome.generated
                totals.explain_ineligible += outcome.explain_ineligible
                totals.explain_failed += outcome.explain_failed
                totals.withheld += outcome.withheld
                totals.relabelled += outcome.relabelled
                totals.technical += outcome.technical
                totals.technical_failed += outcome.technical_failed
                totals.titles_generated += outcome.titles_generated
                totals.title_failed += outcome.title_failed
                totals.failed += outcome.failed
                if outcome.reason:
                    errors.append(f"{story.story_id}: {outcome.reason}")
                if done % 25 == 0 or done == len(pending):
                    print(  # noqa: T201
                        f"  {done}/{len(pending)} "
                        f"generated={totals.generated} "
                        f"withheld={totals.withheld} "
                        f"failed={totals.failed} "
                        f"${totals.cost:.2f}",
                        flush=True,
                    )

        counters: dict[str, Any] = {
            "attempted": len(pending),
            "generated": totals.generated,
            "explain_ineligible": totals.explain_ineligible,
            "explain_failed": totals.explain_failed,
            "withheld_kind": totals.withheld,
            "reopened": reopened,
            "relabelled": totals.relabelled,
            "technical": totals.technical,
            "technical_failed": totals.technical_failed,
            "titles_generated": totals.titles_generated,
            "title_failed": totals.title_failed,
            "failed": totals.failed,
            "cost_usd": round(totals.cost, 4),
        }
        if errors:
            counters["errors"] = errors[:20]

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                  status = %s, finished_at = now(), counters = %s
                WHERE id = %s;
                """,
                (
                    "succeeded" if totals.generated and not errors else "partial",
                    Jsonb(counters),
                    run_id,
                ),
            )

    return GenerationRunResult(
        attempted=len(pending),
        generated=totals.generated,
        explain_ineligible=totals.explain_ineligible,
        explain_failed=totals.explain_failed,
        withheld_kind=totals.withheld,
        relabelled=totals.relabelled,
        technical=totals.technical,
        technical_failed=totals.technical_failed,
        titles_generated=totals.titles_generated,
        title_failed=totals.title_failed,
        failed=totals.failed,
        cost_usd=round(totals.cost, 4),
    )
