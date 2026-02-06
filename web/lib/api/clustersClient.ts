import { env } from '@/lib/config/env';
import { ApiError } from '@/lib/api/errors';
import type { ClusterDetail } from '@/types/api';

type ClusterDetailResult =
  | { kind: 'ok'; cluster: ClusterDetail }
  | { kind: 'redirect'; toId: string }
  | { kind: 'not_found' };

export async function getClusterDetailClient(clusterId: string): Promise<ClusterDetailResult> {
  const url = new URL(`${env.apiUrl}/clusters/${clusterId}`);
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
    credentials: 'include',
    cache: 'no-store',
  });

  if (res.status === 301) {
    const body = (await res.json().catch(() => null)) as { redirect_to_cluster_id?: string } | null;
    if (body?.redirect_to_cluster_id) {
      return { kind: 'redirect', toId: body.redirect_to_cluster_id };
    }
  }

  if (res.status === 404) return { kind: 'not_found' };
  if (!res.ok) {
    const body = await res.json().catch(() => undefined);
    throw new ApiError(res.status, 'http_error', `Request failed: ${res.status}`, body);
  }

  return { kind: 'ok', cluster: (await res.json()) as ClusterDetail };
}

