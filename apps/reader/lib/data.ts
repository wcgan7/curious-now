import { database } from "@/lib/database";
import { mixFormats, spreadSources } from "@/lib/spread";
import { renderMath } from "@/lib/math";
import { renderProse } from "@/lib/prose";
import type {
  Citation,
  Claim,
  ConceptLink,
  Explanation,
  ExplanationDepth,
  FeedPage,
  FeedStory,
  SourceLink,
  StoryDetail,
} from "@/lib/types";

interface LanePosition {
  sortAt: string;
  id: string;
}

// Each editorial lane advances independently. A single global cursor would
// lose the highly ranked stories skipped when a page reserves one third of its
// positions for accessible reporting.
interface Cursor {
  technical: LanePosition | null;
  accessible: LanePosition | null;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface FeedRow {
  id: string;
  reader_title: string;
  sort_at: Date;
  published_at?: Date;
  quality_score: number | null;
  significance: string | null;
  sources: SourceLink[];
}

interface StoryRow extends FeedRow {
  mode: "evidence_only" | "enriched";
  available_depths: ExplanationDepth[];
}

function encodeCursor(cursor: Cursor): string {
  return Buffer.from(JSON.stringify(cursor)).toString("base64url");
}

export function decodeCursor(value: string | null): Cursor | null {
  if (!value) {
    return null;
  }
  try {
    const decoded = JSON.parse(
      Buffer.from(value, "base64url").toString("utf8"),
    ) as unknown;
    const position = (candidate: unknown): LanePosition | null | undefined => {
      if (candidate === null) return null;
      if (typeof candidate !== "object" || candidate === null) return undefined;
      const value = candidate as Partial<LanePosition>;
      if (
        typeof value.sortAt !== "string" ||
        typeof value.id !== "string" ||
        !UUID_PATTERN.test(value.id) ||
        Number.isNaN(Date.parse(value.sortAt))
      ) {
        return undefined;
      }
      return { sortAt: value.sortAt, id: value.id };
    };

    // A cached cursor from the former single-lane feed still describes a
    // meaningful global boundary. Apply it to both lanes so an update does not
    // break someone's restored scroll position.
    const legacy = position(decoded);
    if (legacy) {
      return { technical: legacy, accessible: legacy };
    }
    if (typeof decoded !== "object" || decoded === null) return null;
    const candidate = decoded as Partial<Cursor>;
    const technical = position(candidate.technical);
    const accessible = position(candidate.accessible);
    if (technical === undefined || accessible === undefined) return null;
    if (technical === null && accessible === null) return null;
    return { technical, accessible };
  } catch {
    return null;
  }
}

function mapFeedRow(row: FeedRow): FeedStory {
  return {
    id: row.id,
    title: row.reader_title,
    titleHtml: renderMath(row.reader_title),
    publishedAt: (row.published_at ?? row.sort_at).toISOString(),
    sources: (row.sources ?? []).map((source) => ({
      ...source,
      titleHtml: renderMath(source.title),
    })),
  };
}

export async function getFeedPage(
  cursor: Cursor | null = null,
  pageSize = 20,
  /** Restrict to a set of field leaves, or null for no restriction.
   *
   * It has to be in the query rather than applied to the page afterwards.
   * Filtering a fetched page of twenty left a reader who asked for space with
   * an empty screen, because the head of the feed is homogeneous and every
   * other field is hundreds of rows down. The predicate belongs where the rows
   * are chosen. */
  fieldLeaves: readonly string[] | null = null,
): Promise<FeedPage> {
  const sql = database();
  const fetchLane = async (
    accessible: boolean,
    position: LanePosition | null,
    limit: number,
  ): Promise<FeedRow[]> => {
    if (limit <= 0) return [];
    // effective_at carries the quality adjustment and never changes, so each
    // lane retains stable keyset pagination. The displayed date is the actual
    // publication date, selected separately below; ranking penalties must not
    // make a four-hour-old article tell the reader it is four days old.
    const cursorFilter = position
      ? sql`
          AND (COALESCE(s.effective_at, s.published_at, s.created_at), s.id)
            < (${position.sortAt}::timestamptz, ${position.id}::uuid)
        `
      : sql``;
    const fieldFilter =
      fieldLeaves && fieldLeaves.length > 0
        ? sql`AND s.field = ANY(${fieldLeaves as string[]})`
        : sql``;
    const accessibleCondition = sql`(
      grounding_source.role = 'journalism'
      OR grounding_item.content_type IN ('news', 'press_release', 'blog')
    )`;
    const laneFilter = accessible
      ? sql`AND ${accessibleCondition}`
      : sql`AND NOT ${accessibleCondition}`;

    return sql<FeedRow[]>`
      WITH page AS (
        SELECT
          s.id,
          COALESCE(dt.text, grounding_item.title, s.working_title) AS reader_title,
          COALESCE(s.effective_at, s.published_at, s.created_at) AS sort_at,
          COALESCE(grounding_item.published_at, s.published_at, s.created_at)
            AS published_at,
          s.quality_score,
          s.significance
        FROM stories s
        LEFT JOIN display_titles dt
          ON dt.id = s.current_display_title_id
         AND dt.status = 'valid'
        LEFT JOIN evidence_packets current_ep
          ON current_ep.id = s.current_evidence_packet_id
        LEFT JOIN items grounding_item
          ON grounding_item.id = NULLIF(
            current_ep.provenance->>'grounding_item', ''
          )::uuid
        LEFT JOIN sources grounding_source
          ON grounding_source.id = grounding_item.source_id
        WHERE s.status = 'published'
        ${cursorFilter}
        ${fieldFilter}
        ${laneFilter}
        ORDER BY
          COALESCE(s.effective_at, s.published_at, s.created_at) DESC,
          s.id DESC
        LIMIT ${limit}
      )
      SELECT
        p.*,
        COALESCE(
          jsonb_agg(
            jsonb_build_object(
              'itemId', i.id,
              'sourceName', src.name,
              'sourceRole', src.role,
              'storyRole', si.role,
              'title', i.title,
              'url', i.url,
              'contentType', i.content_type,
              'contentTypeBasis', i.content_type_basis,
              'imageUrl', i.image_url,
              'figureImage', (
                SELECT jsonb_build_object(
                  'url', f->>'image_url',
                  'label', f->>'label',
                  'caption', f->>'caption'
                )
                FROM jsonb_array_elements(
                  COALESCE(i.text_structure->'figures', '[]'::jsonb)
                ) f
                WHERE f->>'image_url' IS NOT NULL
                LIMIT 1
              ),
              'accessClass', i.access_class,
              'publishedAt', i.published_at
            )
            ORDER BY i.published_at DESC NULLS LAST, i.id
          ),
          '[]'::jsonb
        ) AS sources
      FROM page p
      JOIN story_items si ON si.story_id = p.id
      JOIN items i ON i.id = si.item_id
      JOIN sources src ON src.id = i.source_id
      GROUP BY
        p.id,
        p.reader_title,
        p.sort_at,
        p.published_at,
        p.quality_score,
        p.significance
      ORDER BY p.sort_at DESC, p.id DESC;
    `;
  };

  const accessibleLimit = pageSize > 1 ? Math.max(1, Math.floor(pageSize / 3)) : 0;
  const technicalLimit = pageSize - accessibleLimit;
  let [technicalRows, accessibleRows] = await Promise.all([
    fetchLane(false, cursor?.technical ?? null, technicalLimit),
    fetchLane(true, cursor?.accessible ?? null, accessibleLimit),
  ]);

  const missing = pageSize - technicalRows.length - accessibleRows.length;
  if (missing > 0 && technicalRows.length === technicalLimit) {
    technicalRows = await fetchLane(
      false,
      cursor?.technical ?? null,
      technicalLimit + missing,
    );
  } else if (missing > 0 && accessibleRows.length === accessibleLimit) {
    accessibleRows = await fetchLane(
      true,
      cursor?.accessible ?? null,
      accessibleLimit + missing,
    );
  }

  const technicalStories = spreadSources(technicalRows.map(mapFeedRow));
  const accessibleStories = spreadSources(accessibleRows.map(mapFeedRow));
  const stories = mixFormats(technicalStories, accessibleStories);
  const positionOf = (row: FeedRow | undefined): LanePosition | null =>
    row
      ? { sortAt: row.sort_at.toISOString(), id: row.id }
      : null;
  return {
    stories,
    nextCursor:
      stories.length === pageSize
        ? encodeCursor({
            technical:
              positionOf(technicalRows.at(-1)) ?? cursor?.technical ?? null,
            accessible:
              positionOf(accessibleRows.at(-1)) ?? cursor?.accessible ?? null,
          })
        : null,
  };
}

export async function searchStories(
  query: string,
  limit = 30,
): Promise<FeedStory[]> {
  const trimmed = query.trim();
  if (!trimmed) {
    return [];
  }

  const sql = database();
  // Search reaches every title a reader can see: the story's own title, the
  // generated display title, and the retained source titles. Text relevance
  // leads; feed score breaks ties so a strong match still surfaces good
  // evidence first.
  const rows = await sql<FeedRow[]>`
    WITH q AS (SELECT plainto_tsquery('english', ${trimmed}) AS query),
    matches AS (
      SELECT
        s.id,
        max(
          GREATEST(
            ts_rank(s.search_document, q.query),
            COALESCE(ts_rank(dt.search_document, q.query), 0),
            COALESCE(ts_rank(i.search_document, q.query), 0)
          )
        ) AS relevance
      FROM stories s
      CROSS JOIN q
      LEFT JOIN display_titles dt
        ON dt.id = s.current_display_title_id
       AND dt.status = 'valid'
      LEFT JOIN story_items si ON si.story_id = s.id
      LEFT JOIN items i ON i.id = si.item_id
      WHERE s.status = 'published'
        AND (
          s.search_document @@ q.query
          OR dt.search_document @@ q.query
          OR i.search_document @@ q.query
        )
      GROUP BY s.id
    ),
    page AS (
      SELECT
        s.id,
        COALESCE(dt.text, grounding_item.title, s.working_title) AS reader_title,
        -- One alias, not two. The older publication-date version was left
        -- behind when ranking moved to effective_at, and Postgres rejected the
        -- whole query as ambiguous rather than picking one -- so search has
        -- been returning a 500 since that change.
        COALESCE(s.effective_at, s.published_at, s.created_at) AS sort_at,
        m.relevance
      FROM matches m
      JOIN stories s ON s.id = m.id
      LEFT JOIN display_titles dt
        ON dt.id = s.current_display_title_id
       AND dt.status = 'valid'
      LEFT JOIN evidence_packets current_ep
        ON current_ep.id = s.current_evidence_packet_id
      LEFT JOIN items grounding_item
        ON grounding_item.id = NULLIF(
          current_ep.provenance->>'grounding_item', ''
        )::uuid
      ORDER BY m.relevance DESC,
               COALESCE(s.effective_at, s.published_at, s.created_at) DESC, s.id DESC
      LIMIT ${limit}
    )
    SELECT
      p.*,
      COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'itemId', i.id,
            'sourceName', src.name,
            'sourceRole', src.role,
            'storyRole', si.role,
            'title', i.title,
            'url', i.url,
            'contentType', i.content_type,
            'contentTypeBasis', i.content_type_basis,
            'imageUrl', i.image_url,
            -- A paper syndicates no image, but its own first figure can stand
            -- in: a thumbnail identifying a work we link to and explain.
            'figureImage', (
              SELECT jsonb_build_object(
                'url', f->>'image_url',
                'label', f->>'label',
                'caption', f->>'caption'
              )
              FROM jsonb_array_elements(
                COALESCE(i.text_structure->'figures', '[]'::jsonb)
              ) f
              WHERE f->>'image_url' IS NOT NULL
              LIMIT 1
            ),
            'accessClass', i.access_class,
            'publishedAt', i.published_at
          )
          ORDER BY i.published_at DESC NULLS LAST, i.id
        ),
        '[]'::jsonb
      ) AS sources
    FROM page p
    JOIN story_items si ON si.story_id = p.id
    JOIN items i ON i.id = si.item_id
    JOIN sources src ON src.id = i.source_id
    GROUP BY p.id, p.reader_title, p.sort_at, p.relevance
    ORDER BY p.relevance DESC, p.sort_at DESC, p.id DESC;
  `;

  return rows.map(mapFeedRow);
}

/** Prepare the prose inside a legacy structured Technical walkthrough. */
function renderContentMath(content: Record<string, unknown>): Record<string, unknown> {
  const sections = content?.sections;
  if (!Array.isArray(sections)) {
    return content;
  }
  return {
    ...content,
    sections: sections.map((section) =>
      typeof section === "object" && section !== null && "text" in section
        ? {
            ...section,
            blocks: renderProse(String((section as { text: string }).text), {
              inferHeadings: true,
            }),
          }
        : section,
    ),
  };
}

export async function getStory(id: string): Promise<StoryDetail | null> {
  if (!UUID_PATTERN.test(id)) {
    return null;
  }

  const sql = database();
  const storyRows = await sql<StoryRow[]>`
    SELECT
      s.id,
      COALESCE(dt.text, grounding_item.title, s.working_title) AS reader_title,
      COALESCE(s.published_at, s.created_at) AS sort_at,
      CASE WHEN dp.packet_id IS NOT NULL
        THEN 'enriched' ELSE 'evidence_only' END AS mode,
      COALESCE(
        (
          SELECT ARRAY_AGG(d.depth ORDER BY d.ord)
          FROM (
            SELECT DISTINCT
              e.depth,
              CASE e.depth
                WHEN 'glance' THEN 1
                WHEN 'explain' THEN 2
                ELSE 3
              END AS ord
            FROM explanations e
            WHERE e.story_id = s.id
              AND e.evidence_packet_id = dp.packet_id
              AND e.conceptual_spine_id IS NOT DISTINCT FROM dp.spine_id
              AND e.status = 'valid'
          ) d
        ),
        '{}'
      ) AS available_depths,
      (
        SELECT COALESCE(
          jsonb_agg(
            jsonb_build_object(
              'itemId', i.id,
              'sourceName', src.name,
              'sourceRole', src.role,
              'storyRole', si.role,
              'title', i.title,
              'url', i.url,
              'contentType', i.content_type,
            'contentTypeBasis', i.content_type_basis,
            'imageUrl', i.image_url,
            -- A paper syndicates no image, but its own first figure can stand
            -- in: a thumbnail identifying a work we link to and explain.
            'figureImage', (
              SELECT jsonb_build_object(
                'url', f->>'image_url',
                'label', f->>'label',
                'caption', f->>'caption'
              )
              FROM jsonb_array_elements(
                COALESCE(i.text_structure->'figures', '[]'::jsonb)
              ) f
              WHERE f->>'image_url' IS NOT NULL
              LIMIT 1
            ),
              'accessClass', i.access_class,
              'publishedAt', i.published_at
            )
            ORDER BY i.published_at DESC NULLS LAST, i.id
          ),
          '[]'::jsonb
        )
        FROM story_items si
        JOIN items i ON i.id = si.item_id
        JOIN sources src ON src.id = i.source_id
        WHERE si.story_id = s.id
      ) AS sources
    FROM stories s
    LEFT JOIN display_titles dt
      ON dt.id = s.current_display_title_id
     AND dt.status = 'valid'
    LEFT JOIN evidence_packets current_ep
      ON current_ep.id = s.current_evidence_packet_id
    LEFT JOIN items grounding_item
      ON grounding_item.id = NULLIF(
        current_ep.provenance->>'grounding_item', ''
      )::uuid
    LEFT JOIN LATERAL (
      SELECT
        e.evidence_packet_id AS packet_id,
        e.conceptual_spine_id AS spine_id
      FROM explanations e
      WHERE e.story_id = s.id
        AND e.evidence_packet_id = s.current_evidence_packet_id
        AND e.depth = 'glance'
        AND e.status = 'valid'
      ORDER BY e.created_at DESC
      LIMIT 1
    ) dp ON TRUE
    WHERE s.id = ${id}::uuid
      AND s.status = 'published'
    LIMIT 1;
  `;
  const row = storyRows[0];
  if (!row) {
    return null;
  }

  // What this story's paper builds on. Read separately rather than joined into
  // the story row: most stories have no edges, and a lateral aggregate would
  // pay for the join on every one of them.
  const explanationRows = await sql<
    Array<{
      depth: ExplanationDepth;
      plain_text: string | null;
      content: Record<string, unknown>;
    }>
  >`
    WITH dp AS (
      SELECT
        e.evidence_packet_id AS packet_id,
        e.conceptual_spine_id AS spine_id
      FROM stories s
      JOIN explanations e
        ON e.story_id = s.id
       AND e.evidence_packet_id = s.current_evidence_packet_id
      WHERE s.id = ${id}::uuid
        AND e.depth = 'glance'
        AND e.status = 'valid'
      ORDER BY e.created_at DESC
      LIMIT 1
    )
    SELECT DISTINCT ON (e.depth)
      e.depth,
      e.plain_text,
      e.content
    FROM explanations e, dp
    WHERE e.story_id = ${id}::uuid
      AND e.evidence_packet_id = dp.packet_id
      AND e.conceptual_spine_id IS NOT DISTINCT FROM dp.spine_id
      AND e.status = 'valid'
    ORDER BY
      e.depth,
      e.created_at DESC;
  `;
  const explanations: Explanation[] = explanationRows.map((value) => ({
    depth: value.depth,
    plainText: value.plain_text,
    // Kept null for compatibility with cached clients. The blocks below carry
    // the rendered HTML once; sending the old flat rendering as well nearly
    // doubles a math-heavy Technical payload.
    html: null,
    blocks: value.plain_text
      ? renderProse(value.plain_text, { inferHeadings: value.depth !== "glance" })
      : [],
    content: renderContentMath(value.content ?? {}),
  }));

  const claimRows = await sql<
    Array<{
      id: string;
      claim_kind: string;
      claim_text: string;
      confidence: number;
      citations: Citation[];
    }>
  >`
    SELECT
      ec.id,
      ec.claim_kind,
      ec.claim_text,
      ec.confidence,
      COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'itemId', i.id,
            'sourceName', src.name,
            'url', i.url,
            'excerpt', ce.excerpt,
            'locator', ce.locator
          )
          ORDER BY src.name, i.id
        ) FILTER (WHERE ce.id IS NOT NULL),
        '[]'::jsonb
      ) AS citations
    FROM stories s
    JOIN evidence_claims ec
      ON ec.evidence_packet_id = s.current_evidence_packet_id
    LEFT JOIN claim_evidence ce ON ce.claim_id = ec.id
    LEFT JOIN items i ON i.id = ce.item_id
    LEFT JOIN sources src ON src.id = i.source_id
    WHERE s.id = ${id}::uuid
    GROUP BY ec.id
    ORDER BY ec.ordinal;
  `;
  const claims: Claim[] = claimRows.map((value) => ({
    id: value.id,
    kind: value.claim_kind,
    text: value.claim_text,
    confidence: value.confidence,
    citations: value.citations ?? [],
  }));

  const concepts = await sql<ConceptLink[]>`
    SELECT c.slug, c.name, sc.relevance
    FROM story_concepts sc
    JOIN concepts c ON c.id = sc.concept_id
    WHERE sc.story_id = ${id}::uuid
      AND c.status = 'published'
    ORDER BY
      CASE sc.relevance
        WHEN 'prerequisite' THEN 1
        WHEN 'central' THEN 2
        ELSE 3
      END,
      c.name;
  `;

  const base = mapFeedRow(row);

  return {
    ...base,
    // Typeset the figure caption here, with the same KaTeX the prose uses and
    // for the same reason: 134 of the corpus's 291 figure captions carry
    // LaTeX, so nearly half of them would otherwise read "Level scheme of
    // \(Q_{x}\)-transition". The feed never shows a caption, so this happens
    // on the story page only.
    sources: base.sources.map((source) =>
      source.figureImage?.caption
        ? {
            ...source,
            figureImage: {
              ...source.figureImage,
              captionHtml: renderMath(source.figureImage.caption),
            },
          }
        : source,
    ),
    mode: row.mode,
    availableDepths: row.available_depths ?? [],
    claims,
    explanations,
    concepts: [...concepts],
  };
}
