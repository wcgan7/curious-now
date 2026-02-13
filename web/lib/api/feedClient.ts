'use client';

import { env } from '@/lib/config/env';
import type { ClustersFeedResponse, ContentType } from '@/types/api';

export async function getFeedClient(options: {
  tab: 'latest' | 'trending';
  page: number;
  pageSize: number;
  topicId?: string;
  contentType?: ContentType;
}): Promise<ClustersFeedResponse> {
  const url = new URL(`${env.apiUrl}/feed`);
  url.searchParams.set('tab', options.tab);
  url.searchParams.set('page', String(options.page));
  url.searchParams.set('page_size', String(options.pageSize));
  if (options.topicId) url.searchParams.set('topic_id', options.topicId);
  if (options.contentType) url.searchParams.set('content_type', options.contentType);

  const res = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (!res.ok) {
    throw new Error(`Feed request failed: ${res.status}`);
  }

  return (await res.json()) as ClustersFeedResponse;
}
