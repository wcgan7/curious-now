import { http, HttpResponse } from 'msw';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

export const handlers = [
  http.get(`${API}/user`, () => {
    return HttpResponse.json({ detail: 'Unauthenticated' }, { status: 401 });
  }),
  http.get(`${API}/user/prefs`, () => {
    return HttpResponse.json(
      {
        prefs: {
          reading_mode_default: 'intuition',
          followed_topic_ids: [],
          followed_entity_ids: [],
          blocked_source_ids: [],
          saved_cluster_ids: [],
          hidden_cluster_ids: [],
          notification_settings: {},
        },
      },
      { status: 200 }
    );
  }),
  http.patch(`${API}/user/prefs`, async ({ request }) => {
    const patch = (await request.json().catch(() => ({}))) as any;
    return HttpResponse.json(
      {
        prefs: {
          reading_mode_default: patch.reading_mode_default || 'intuition',
          followed_topic_ids: [],
          followed_entity_ids: [],
          blocked_source_ids: [],
          saved_cluster_ids: [],
          hidden_cluster_ids: [],
          notification_settings: patch.notification_settings || {},
        },
      },
      { status: 200 }
    );
  }),
  http.post(`${API}/auth/magic_link/start`, () => {
    return HttpResponse.json({ status: 'sent' }, { status: 200 });
  }),
  http.post(`${API}/auth/magic_link/verify`, () => {
    return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
  }),
  http.get(`${API}/user/saves`, () => {
    return HttpResponse.json(
      {
        saved: [],
      },
      { status: 200 }
    );
  }),
  http.post(`${API}/user/saves/:clusterId`, () => {
    return HttpResponse.json({ status: 'ok' }, { status: 200 });
  }),
  http.delete(`${API}/user/saves/:clusterId`, () => {
    return HttpResponse.json({ status: 'ok' }, { status: 200 });
  }),
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
              confidence_band: null,
              takeaway: 'Short takeaway',
              anti_hype_flags: [],
            },
          ],
          topics: [
            { topic_id: '00000000-0000-0000-0000-000000000010', name: 'Artificial Intelligence' },
          ],
        },
        { status: 200 }
      );
    }
    return HttpResponse.json({ query: q, clusters: [], topics: [] }, { status: 200 });
  }),
];
