import { headers } from 'next/headers';

import { env } from '@/lib/config/env';
import type { ClusterUpdatesResponse } from '@/types/api';

type ClusterUpdatesResult =
  | { kind: 'ok'; updates: ClusterUpdatesResponse }
  | { kind: 'redirect'; toId: string }
  | { kind: 'not_found' };

export async function getClusterUpdates(clusterId: string): Promise<ClusterUpdatesResult> {
  const url = new URL(`${env.apiUrl}/clusters/${clusterId}/updates`);
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
    const body = (await res.json()) as { redirect_to_cluster_id?: string };
    if (body.redirect_to_cluster_id) {
      return { kind: 'redirect', toId: body.redirect_to_cluster_id };
    }
  }

  if (res.status === 404) return { kind: 'not_found' };
  if (!res.ok) throw new Error(`Updates request failed: ${res.status}`);
  return { kind: 'ok', updates: (await res.json()) as ClusterUpdatesResponse };
}
