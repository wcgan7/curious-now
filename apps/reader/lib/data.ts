import { database } from "@/lib/database";
import { orderLineage } from "@/lib/lineage";
import { spreadSources } from "@/lib/spread";
import { renderMath } from "@/lib/math";
import type {
  Citation,
  Claim,
  ConceptLink,
  Explanation,
  ExplanationDepth,
  FeedPage,
  FeedStory,
  LineageEdge,
  SourceLink,
  StoryDetail,
} from "@/lib/types";

// Two fields, not three: effective_at already carries quality, so there is no
// separate score to page on. A cursor minted before that change simply fails to
// decode and the reader starts from the top, which is the right degradation.
interface Cursor {
  sortAt: string;
  id: string;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface FeedRow {
  id: string;
  reader_title: string;
  sort_at: Date;
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
    title: row.reader_title,
    publishedAt: row.sort_at.toISOString(),
    sources: row.sources ?? [],
  };
}

export async function getFeedPage(
  cursor: Cursor | null = null,
  pageSize = 20,
): Promise<FeedPage> {
  const sql = database();
  // effective_at is the story's publication date shifted earlier by what its
  // quality cost it, so ordering by it alone is the ranked order. It is
  // time-invariant, which is what makes keyset pagination stable here: the key
  // cannot move under a reader mid-scroll the way a decaying score would.
  // Stories without one fall back to their publication date.
  const cursorFilter = cursor
    ? sql`
        AND (COALESCE(s.effective_at, s.published_at, s.created_at), s.id)
          < (${cursor.sortAt}::timestamptz, ${cursor.id}::uuid)
      `
    : sql``;

  const rows = await sql<FeedRow[]>`
    WITH page AS (
      SELECT
        s.id,
        COALESCE(dt.text, s.working_title) AS reader_title,
        COALESCE(s.effective_at, s.published_at, s.created_at) AS sort_at,
        s.quality_score,
        s.significance
      FROM stories s
      LEFT JOIN display_titles dt
        ON dt.id = s.current_display_title_id
       AND dt.status = 'valid'
      WHERE s.status = 'published'
      ${cursorFilter}
      ORDER BY
        COALESCE(s.effective_at, s.published_at, s.created_at) DESC,
        s.id DESC
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
            'contentTypeBasis', i.content_type_basis,
            'imageUrl', i.image_url,
            -- A paper syndicates no image, but its own first figure can stand
            -- in: a thumbnail identifying a work we link to and explain.
            'figureImage', (
              SELECT jsonb_build_object('url', f->>'image_url', 'label', f->>'label')
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
      p.quality_score,
      p.significance
    ORDER BY p.sort_at DESC, p.id DESC;
  `;

  // The cursor is minted from the SQL order, before interleaving, so every
  // story falls on exactly one page and the keyset stays stable. Interleaving
  // only changes the reading order within the page it was already on.
  const lastRow = rows.at(-1);
  const stories = spreadSources(rows.map(mapFeedRow));
  return {
    stories,
    nextCursor:
      rows.length === pageSize && lastRow
        ? encodeCursor({
            sortAt: lastRow.sort_at.toISOString(),
            id: lastRow.id,
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
        COALESCE(dt.text, s.working_title) AS reader_title,
        COALESCE(s.published_at, s.created_at) AS sort_at,
        COALESCE(s.effective_at, s.published_at, s.created_at) AS sort_at,
        m.relevance
      FROM matches m
      JOIN stories s ON s.id = m.id
      LEFT JOIN display_titles dt
        ON dt.id = s.current_display_title_id
       AND dt.status = 'valid'
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
              SELECT jsonb_build_object('url', f->>'image_url', 'label', f->>'label')
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

/** Typeset the mathematics inside a Technical walkthrough's sections. */
function renderContentMath(content: Record<string, unknown>): Record<string, unknown> {
  const sections = content?.sections;
  if (!Array.isArray(sections)) {
    return content;
  }
  return {
    ...content,
    sections: sections.map((section) =>
      typeof section === "object" && section !== null && "text" in section
        ? { ...section, html: renderMath(String((section as { text: string }).text)) }
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
      COALESCE(dt.text, s.working_title) AS reader_title,
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
              SELECT jsonb_build_object('url', f->>'image_url', 'label', f->>'label')
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
    LEFT JOIN LATERAL (
      SELECT
        e.evidence_packet_id AS packet_id,
        e.conceptual_spine_id AS spine_id
      FROM explanations e
      JOIN evidence_packets ep ON ep.id = e.evidence_packet_id
      WHERE e.story_id = s.id
        AND e.status = 'valid'
      ORDER BY ep.version DESC, e.created_at DESC
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
  const lineageRows = await sql<
    Array<{
      relation: LineageEdge["relation"];
      title: string;
      doi: string | null;
      arxiv_id: string | null;
      quote: string | null;
    }>
  >`
    SELECT DISTINCT ON (r.to_paper_id, r.relation)
      r.relation,
      target.title,
      target.doi,
      target.arxiv_id,
      r.provenance->>'quote' AS quote
    FROM story_items si
    JOIN item_papers ip ON ip.item_id = si.item_id
    JOIN paper_relations r ON r.from_paper_id = ip.paper_id
    JOIN papers target ON target.id = r.to_paper_id
    WHERE si.story_id = ${id}::uuid
      AND r.provenance->>'quote' IS NOT NULL
    ORDER BY r.to_paper_id, r.relation, r.created_at DESC;
  `;

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
      FROM explanations e
      JOIN evidence_packets ep ON ep.id = e.evidence_packet_id
      WHERE e.story_id = ${id}::uuid
        AND e.status = 'valid'
      ORDER BY ep.version DESC, e.created_at DESC
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
    // Typeset here rather than in the component: KaTeX runs on the server and
    // stays out of the browser bundle, and the client receives finished HTML.
    html: value.plain_text ? renderMath(value.plain_text) : null,
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
      ON ec.evidence_packet_id = COALESCE(
        (
          -- Claims follow the displayed explanation set so one reader
          -- session never mixes evidence-packet versions.
          SELECT e.evidence_packet_id
          FROM explanations e
          JOIN evidence_packets ep ON ep.id = e.evidence_packet_id
          WHERE e.story_id = s.id
            AND e.status = 'valid'
          ORDER BY ep.version DESC, e.created_at DESC
          LIMIT 1
        ),
        s.current_evidence_packet_id
      )
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
    mode: row.mode,
    availableDepths: row.available_depths ?? [],
    claims,
    explanations,
    concepts: [...concepts],
    lineage: orderLineage(
      lineageRows.map((edge) => ({
        relation: edge.relation,
        title: edge.title,
        doi: edge.doi,
        arxivId: edge.arxiv_id,
        quote: edge.quote ?? "",
      })),
    ),
  };
}
