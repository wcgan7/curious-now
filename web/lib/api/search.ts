import { apiFetch } from '@/lib/api/client';
import type { SearchResponse } from '@/types/api';

export async function search(q: string): Promise<SearchResponse> {
  const { data } = await apiFetch<SearchResponse>('/search', {
    method: 'GET',
    params: { q },
  });
  return data;
}

