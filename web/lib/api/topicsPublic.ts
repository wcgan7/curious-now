import { apiFetch } from '@/lib/api/client';
import type { TopicsResponse } from '@/types/api';

export async function listTopics(): Promise<TopicsResponse> {
  const { data } = await apiFetch<TopicsResponse>('/topics', { method: 'GET' });
  return data;
}

