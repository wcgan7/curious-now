import { describe, expect, it, vi } from 'vitest';

import { getClusterDetail } from './clusters';

vi.mock('next/headers', () => {
  return {
    headers: async () => new Headers(),
  };
});

describe('lib/api/clusters', () => {
  it('returns redirect result on 301 redirect payload', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ redirect_to_cluster_id: 'to-id' }), {
          status: 301,
          headers: { 'content-type': 'application/json' },
        })
      );

    const res = await getClusterDetail('from-id');
    expect(res).toEqual({ kind: 'redirect', toId: 'to-id' });
    fetchMock.mockRestore();
  });

  it('returns not_found on 404', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('not found', { status: 404 }));

    const res = await getClusterDetail('missing');
    expect(res).toEqual({ kind: 'not_found' });
    fetchMock.mockRestore();
  });
});

