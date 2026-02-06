import { apiFetch } from '@/lib/api/client';
import type { SourcesResponse } from '@/types/api';

export async function listSources(): Promise<SourcesResponse> {
  const { data } = await apiFetch<SourcesResponse>('/sources', { method: 'GET' });
  return data;
}

