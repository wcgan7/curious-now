import { headers } from 'next/headers';

import { env } from '@/lib/config/env';
import type { ClustersFeedResponse, ContentType } from '@/types/api';

export async function getFeed(options: {
  tab: 'latest' | 'trending' | 'for_you';
  page?: number;
  pageSize?: number;
  topicId?: string;
  contentType?: ContentType;
}): Promise<ClustersFeedResponse> {
  const url = new URL(`${env.apiUrl}/feed`);
  url.searchParams.set('tab', options.tab);
  url.searchParams.set('page', String(options.page ?? 1));
  url.searchParams.set('page_size', String(options.pageSize ?? 20));
  if (options.topicId) url.searchParams.set('topic_id', options.topicId);
  if (options.contentType) url.searchParams.set('content_type', options.contentType);

  const cookie = (await headers()).get('cookie');
  const res = await fetch(url, {
    headers: {
      ...(cookie ? { cookie } : {}),
      Accept: 'application/json',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (!res.ok) {
    // Feed returns 401 when tab=for_you and unauthenticated
    if (res.status === 401) {
      const err = new Error('unauthorized');
      (err as any).status = 401;
      throw err;
    }
    throw new Error(`Feed request failed: ${res.status}`);
  }

  return (await res.json()) as ClustersFeedResponse;
}
