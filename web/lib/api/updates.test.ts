import { describe, expect, it, vi } from 'vitest';

import { getClusterUpdates } from './updates';

vi.mock('next/headers', () => {
  return {
    headers: async () => new Headers(),
  };
});

describe('lib/api/updates', () => {
  it('returns redirect on 301 with redirect_to_cluster_id', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ redirect_to_cluster_id: 'to-id' }), {
          status: 301,
          headers: { 'content-type': 'application/json' },
        })
      );

    const res = await getClusterUpdates('from-id');
    expect(res).toEqual({ kind: 'redirect', toId: 'to-id' });
    fetchMock.mockRestore();
  });
});

