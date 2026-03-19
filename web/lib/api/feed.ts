import { headers } from 'next/headers';

import { env } from '@/lib/config/env';
import type { ClustersFeedResponse, ContentType } from '@/types/api';

export async function getFeed(options: {
  tab: 'latest' | 'trending';
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

  const maxRetries = 3;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(url, {
        headers: {
          ...(cookie ? { cookie } : {}),
          Accept: 'application/json',
        },
        credentials: 'include',
        cache: 'no-store',
      });

      if (!res.ok) {
        throw new Error(`Feed request failed: ${res.status}`);
      }

      return (await res.json()) as ClustersFeedResponse;
    } catch (err) {
      if (attempt === maxRetries) throw err;
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
  }

  // Unreachable, but satisfies TypeScript
  throw new Error('Feed request failed after retries');
}
