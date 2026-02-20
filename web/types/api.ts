import type { components } from '@/types/api.generated';

export type ContentType = components['schemas']['ContentType'];
export type ClustersFeedResponse = components['schemas']['ClustersFeedResponse'];
export type GlossaryLookupResponse = components['schemas']['GlossaryLookupResponse'];
export type TopicLineageResponse = components['schemas']['TopicLineageResponse'];
export type ClusterUpdatesResponse = components['schemas']['ClusterUpdatesResponse'];
export type Source = components['schemas']['Source'];
export type SourcesResponse = components['schemas']['SourcesResponse'];
export type User = components['schemas']['User'];
export type UserResponse = components['schemas']['UserResponse'];
export type UserPrefs = components['schemas']['UserPrefs'];
export type UserPrefsResponse = components['schemas']['UserPrefsResponse'];
export type UserPrefsPatchRequest = components['schemas']['UserPrefsPatchRequest'];
export type SimpleOkResponse = components['schemas']['SimpleOkResponse'];
export type UserSavesResponse = components['schemas']['UserSavesResponse'];
export type UserWatchesResponse = components['schemas']['UserWatchesResponse'];
export type AuthMagicLinkStartResponse = components['schemas']['AuthMagicLinkStartResponse'];
export type AuthMagicLinkVerifyResponse = components['schemas']['AuthMagicLinkVerifyResponse'];
export type LogoutResponse = components['schemas']['LogoutResponse'];

// Extended types with image URL and category support (until api.generated.ts is regenerated)
export type EvidenceItem = components['schemas']['EvidenceItem'] & {
  image_url?: string | null;
};

export type CategoryChip = {
  category_id: string;
  name: string;
  score: number;
};

export type Topic = components['schemas']['Topic'] & {
  parent_topic_id?: string | null;
  topic_type?: 'category' | 'subtopic' | null;
};

export type TopicDetail = {
  topic: Topic;
  latest_clusters: ClusterCard[];
  trending_clusters?: ClusterCard[];
};

export type TopicsResponse = {
  topics: Topic[];
};

export type SearchResponse = {
  query: string;
  clusters: ClusterCard[];
  topics?: Topic[] | null;
};

export type ClusterCard = components['schemas']['ClusterCard'] & {
  featured_image_url?: string | null;
  top_categories?: CategoryChip[];
  impact_score?: number;
  in_focus_label?: boolean;
};

export type ClusterDetail = components['schemas']['ClusterDetail'] & {
  featured_image_url?: string | null;
  evidence: Record<string, EvidenceItem[]>;
  categories?: CategoryChip[];
};
