import { http, HttpResponse } from 'msw';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

export const handlers = [
  http.get(`${API}/sources`, () => {
    return HttpResponse.json(
      {
        sources: [
          {
            source: {
              source_id: 's1',
              name: 'Example Source',
              homepage_url: null,
              source_type: 'journalism',
              reliability_tier: 'tier1',
              active: true,
            },
            feeds: [],
          },
        ],
      },
      { status: 200 }
    );
  }),
  http.get(`${API}/search`, ({ request }) => {
    const url = new URL(request.url);
    const q = (url.searchParams.get('q') || '').toLowerCase();
    if (!q) return HttpResponse.json({ query: '', clusters: [] }, { status: 200 });
    if (q.includes('ai')) {
      return HttpResponse.json(
        {
          query: q,
          clusters: [
            {
              cluster_id: '00000000-0000-0000-0000-000000000001',
              canonical_title: 'AI does a thing',
              updated_at: new Date().toISOString(),
              distinct_source_count: 2,
              top_topics: [],
              content_type_badges: ['news'],
              takeaway: 'Short takeaway',
              anti_hype_flags: [],
            },
          ],
          topics: [
            {
              topic_id: '00000000-0000-0000-0000-000000000010',
              name: 'Artificial Intelligence',
              topic_type: 'category',
            },
          ],
        },
        { status: 200 }
      );
    }
    return HttpResponse.json({ query: q, clusters: [], topics: [] }, { status: 200 });
  }),
];
