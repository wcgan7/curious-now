import { database } from "@/lib/database";
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

interface Cursor {
  sortAt: string;
  id: string;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface FeedRow {
  id: string;
  canonical_title: string;
  sort_at: Date;
  mode: "evidence_only" | "enriched";
  glance: string | null;
  available_depths: ExplanationDepth[];
  sources: SourceLink[];
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
    ) as Partial<Cursor>;
    if (
      typeof decoded.sortAt !== "string" ||
      typeof decoded.id !== "string" ||
      !UUID_PATTERN.test(decoded.id) ||
      Number.isNaN(Date.parse(decoded.sortAt))
    ) {
      return null;
    }
    return { sortAt: decoded.sortAt, id: decoded.id };
  } catch {
    return null;
  }
}

function mapFeedRow(row: FeedRow): FeedStory {
  return {
    id: row.id,
    title: row.canonical_title,
    publishedAt: row.sort_at.toISOString(),
    mode: row.mode,
    glance: row.glance,
    availableDepths: row.available_depths ?? [],
    sources: row.sources ?? [],
  };
}

export async function getFeedPage(
  cursor: Cursor | null = null,
  pageSize = 20,
): Promise<FeedPage> {
  const sql = database();
  const cursorFilter = cursor
    ? sql`
        AND (COALESCE(s.published_at, s.created_at), s.id)
          < (${cursor.sortAt}::timestamptz, ${cursor.id}::uuid)
      `
    : sql``;

  const rows = await sql<FeedRow[]>`
    WITH page AS (
      SELECT
        s.id,
        s.canonical_title,
        COALESCE(s.published_at, s.created_at) AS sort_at,
        CASE WHEN EXISTS (
          SELECT 1
          FROM explanations e
          WHERE e.story_id = s.id
            AND e.evidence_packet_id = s.current_evidence_packet_id
            AND e.status = 'valid'
        ) THEN 'enriched' ELSE 'evidence_only' END AS mode,
        (
          SELECT e.plain_text
          FROM explanations e
          WHERE e.story_id = s.id
            AND e.evidence_packet_id = s.current_evidence_packet_id
            AND e.status = 'valid'
            AND e.depth = 'glance'
          ORDER BY e.created_at DESC
          LIMIT 1
        ) AS glance,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN EXISTS (
            SELECT 1 FROM explanations e
            WHERE e.story_id = s.id
              AND e.evidence_packet_id = s.current_evidence_packet_id
              AND e.status = 'valid' AND e.depth = 'glance'
          ) THEN 'glance' END,
          CASE WHEN EXISTS (
            SELECT 1 FROM explanations e
            WHERE e.story_id = s.id
              AND e.evidence_packet_id = s.current_evidence_packet_id
              AND e.status = 'valid' AND e.depth = 'explain'
          ) THEN 'explain' END,
          CASE WHEN EXISTS (
            SELECT 1 FROM explanations e
            WHERE e.story_id = s.id
              AND e.evidence_packet_id = s.current_evidence_packet_id
              AND e.status = 'valid' AND e.depth = 'technical'
          ) THEN 'technical' END
        ], NULL) AS available_depths
      FROM stories s
      WHERE s.status = 'published'
      ${cursorFilter}
      ORDER BY COALESCE(s.published_at, s.created_at) DESC, s.id DESC
      LIMIT ${pageSize}
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
      p.canonical_title,
      p.sort_at,
      p.mode,
      p.glance,
      p.available_depths
    ORDER BY p.sort_at DESC, p.id DESC;
  `;

  const stories = rows.map(mapFeedRow);
  const last = stories.at(-1);
  return {
    stories,
    nextCursor:
      rows.length === pageSize && last
        ? encodeCursor({ sortAt: last.publishedAt, id: last.id })
        : null,
  };
}

interface StoryRow extends FeedRow {}

export async function getStory(id: string): Promise<StoryDetail | null> {
  if (!UUID_PATTERN.test(id)) {
    return null;
  }

  const sql = database();
  const storyRows = await sql<StoryRow[]>`
    SELECT
      s.id,
      s.canonical_title,
      COALESCE(s.published_at, s.created_at) AS sort_at,
      CASE WHEN EXISTS (
        SELECT 1 FROM explanations e
        WHERE e.story_id = s.id
          AND e.evidence_packet_id = s.current_evidence_packet_id
          AND e.status = 'valid'
      ) THEN 'enriched' ELSE 'evidence_only' END AS mode,
      (
        SELECT e.plain_text FROM explanations e
        WHERE e.story_id = s.id
          AND e.evidence_packet_id = s.current_evidence_packet_id
          AND e.status = 'valid' AND e.depth = 'glance'
        ORDER BY e.created_at DESC LIMIT 1
      ) AS glance,
      ARRAY_REMOVE(ARRAY[
        CASE WHEN EXISTS (
          SELECT 1 FROM explanations e
          WHERE e.story_id = s.id
            AND e.evidence_packet_id = s.current_evidence_packet_id
            AND e.status = 'valid' AND e.depth = 'glance'
        ) THEN 'glance' END,
        CASE WHEN EXISTS (
          SELECT 1 FROM explanations e
          WHERE e.story_id = s.id
            AND e.evidence_packet_id = s.current_evidence_packet_id
            AND e.status = 'valid' AND e.depth = 'explain'
        ) THEN 'explain' END,
        CASE WHEN EXISTS (
          SELECT 1 FROM explanations e
          WHERE e.story_id = s.id
            AND e.evidence_packet_id = s.current_evidence_packet_id
            AND e.status = 'valid' AND e.depth = 'technical'
        ) THEN 'technical' END
      ], NULL) AS available_depths,
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
    WHERE s.id = ${id}::uuid
      AND s.status = 'published'
    LIMIT 1;
  `;
  const row = storyRows[0];
  if (!row) {
    return null;
  }

  const explanationRows = await sql<
    Array<{
      depth: ExplanationDepth;
      plain_text: string | null;
      content: Record<string, unknown>;
    }>
  >`
    SELECT DISTINCT ON (e.depth)
      e.depth,
      e.plain_text,
      e.content
    FROM explanations e
    JOIN stories s ON s.id = e.story_id
    WHERE e.story_id = ${id}::uuid
      AND e.evidence_packet_id = s.current_evidence_packet_id
      AND e.status = 'valid'
    ORDER BY
      e.depth,
      e.created_at DESC;
  `;
  const explanations: Explanation[] = explanationRows.map((value) => ({
    depth: value.depth,
    plainText: value.plain_text,
    content: value.content ?? {},
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

  return {
    ...mapFeedRow(row),
    claims,
    explanations,
    concepts: [...concepts],
  };
}
