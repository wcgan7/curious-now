import { describe, expect, it, vi } from 'vitest';

import { getTopicDetail } from './topics';

vi.mock('next/headers', () => {
  return {
    headers: async () => new Headers(),
  };
});

describe('lib/api/topics', () => {
  it('returns redirect result on 301 redirect payload', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ redirect_to_topic_id: 'to-topic' }), {
          status: 301,
          headers: { 'content-type': 'application/json' },
        })
      );

    const res = await getTopicDetail('from-topic');
    expect(res).toEqual({ kind: 'redirect', toId: 'to-topic' });
    fetchMock.mockRestore();
  });
});

