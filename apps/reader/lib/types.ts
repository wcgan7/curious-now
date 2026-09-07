export type SourceRole =
  | "primary_research"
  | "journalism"
  | "lab_announcement"
  | "institutional"
  | "government"
  | "press_release"
  | "discovery";

export type ContentType =
  | "news"
  | "lab_announcement"
  | "press_release"
  | "preprint"
  | "peer_reviewed"
  | "report"
  | "blog"
  | "dataset"
  | "other";

export type ExplanationDepth = "glance" | "explain" | "technical";
export type ReaderMode = "evidence_only" | "enriched";

export interface ProseFragment {
  text: string;
  html: string;
}

export type ProseBlock =
  | { kind: "paragraph"; value: ProseFragment }
  | { kind: "heading"; level: 2 | 3; value: ProseFragment }
  | { kind: "quote"; value: ProseFragment }
  | { kind: "list"; ordered: boolean; items: ProseFragment[] };

export type ContentTypeBasis =
  | "feed_default"
  | "feed_unmatched"
  | "source_pattern"
  | "document"
  | "classifier";

export interface SourceLink {
  itemId: string;
  sourceName: string;
  sourceRole: SourceRole;
  storyRole: string;
  title: string;
  // Server-rendered KaTeX with all surrounding prose escaped. Optional so a
  // feed cached before title typesetting shipped still renders as plain text.
  titleHtml?: string;
  url: string;
  contentType: ContentType;
  // Where contentType came from. 'feed_unmatched' means the feed carries
  // several kinds and none of its rules recognised this one, so nothing about
  // its review status has been established.
  contentTypeBasis: ContentTypeBasis;
  // The image the publisher syndicated with this story, hotlinked from
  // their CDN. Null for every paper source — no preprint server or
  // journal supplies one — so absence is the common case.
  imageUrl: string | null;
  // A paper's own first figure, where the source syndicated no image. Shown
  // with its label, because a diagram from the work is not a photograph of it
  // and a reader should be able to tell which they are looking at.
  // The caption travels with it because a figure's caption is the paper's own
  // account of what the figure shows, and on the story page it is the only
  // sentence on the picture that the reader can trust absolutely.
  figureImage: {
    url: string;
    label: string | null;
    caption: string | null;
    // The same caption with its mathematics typeset, rendered on the server.
    // Set on the story page and absent in the feed, which shows no caption.
    captionHtml?: string;
  } | null;
  accessClass: string;
  publishedAt: string | null;
}

export interface FeedStory {
  id: string;
  title: string;
  titleHtml?: string;
  publishedAt: string;
  sources: SourceLink[];
}

export interface FeedPage {
  stories: FeedStory[];
  nextCursor: string | null;
}

export interface Citation {
  itemId: string;
  sourceName: string;
  url: string;
  excerpt: string | null;
  locator: Record<string, string | number>;
}

export interface Claim {
  id: string;
  kind: string;
  text: string;
  confidence: number;
  citations: Citation[];
}

export interface Explanation {
  depth: ExplanationDepth;
  plainText: string | null;
  // The same prose with its mathematics typeset, rendered on the server.
  html: string | null;
  blocks: ProseBlock[];
  content: Record<string, unknown>;
}

export interface ConceptLink {
  slug: string;
  name: string;
  relevance: string;
}

export interface StoryDetail extends FeedStory {
  mode: ReaderMode;
  availableDepths: ExplanationDepth[];
  claims: Claim[];
  explanations: Explanation[];
  concepts: ConceptLink[];
}
