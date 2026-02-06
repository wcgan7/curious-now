import { headers } from 'next/headers';

import { env } from '@/lib/config/env';
import type { TopicDetail, TopicLineageResponse } from '@/types/api';

type TopicDetailResult =
  | { kind: 'ok'; detail: TopicDetail }
  | { kind: 'redirect'; toId: string }
  | { kind: 'not_found' };

export async function getTopicDetail(topicId: string): Promise<TopicDetailResult> {
  const url = new URL(`${env.apiUrl}/topics/${topicId}`);
  const cookie = (await headers()).get('cookie');
  const res = await fetch(url, {
    headers: {
      ...(cookie ? { cookie } : {}),
      Accept: 'application/json',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (res.status === 301) {
    const body = (await res.json()) as { redirect_to_topic_id?: string };
    if (body.redirect_to_topic_id) {
      return { kind: 'redirect', toId: body.redirect_to_topic_id };
    }
  }

  if (res.status === 404) return { kind: 'not_found' };
  if (!res.ok) throw new Error(`Topic request failed: ${res.status}`);
  return { kind: 'ok', detail: (await res.json()) as TopicDetail };
}

type TopicLineageResult =
  | { kind: 'ok'; lineage: TopicLineageResponse }
  | { kind: 'redirect'; toId: string }
  | { kind: 'not_found' };

export async function getTopicLineage(topicId: string): Promise<TopicLineageResult> {
  const url = new URL(`${env.apiUrl}/topics/${topicId}/lineage`);
  const cookie = (await headers()).get('cookie');
  const res = await fetch(url, {
    headers: {
      ...(cookie ? { cookie } : {}),
      Accept: 'application/json',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (res.status === 301) {
    const body = (await res.json()) as { redirect_to_topic_id?: string };
    if (body.redirect_to_topic_id) {
      return { kind: 'redirect', toId: body.redirect_to_topic_id };
    }
  }

  if (res.status === 404) return { kind: 'not_found' };
  if (!res.ok) throw new Error(`Topic lineage failed: ${res.status}`);
  return { kind: 'ok', lineage: (await res.json()) as TopicLineageResponse };
}
