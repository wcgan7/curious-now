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

export interface SourceLink {
  itemId: string;
  sourceName: string;
  sourceRole: SourceRole;
  storyRole: string;
  title: string;
  url: string;
  contentType: ContentType;
  accessClass: string;
  publishedAt: string | null;
}

export interface FeedStory {
  id: string;
  title: string;
  publishedAt: string;
  mode: ReaderMode;
  glance: string | null;
  availableDepths: ExplanationDepth[];
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
  content: Record<string, unknown>;
}

export interface ConceptLink {
  slug: string;
  name: string;
  relevance: string;
}

export interface StoryDetail extends FeedStory {
  claims: Claim[];
  explanations: Explanation[];
  concepts: ConceptLink[];
}
