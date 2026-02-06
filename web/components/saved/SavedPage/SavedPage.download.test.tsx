import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

const saveClusterOfflineMock = vi.fn(async () => {});
const enforceStorageLimitMock = vi.fn(async () => {});
const isClusterAvailableOfflineMock = vi.fn(async () => false);

vi.mock('@/lib/offline/db', () => {
  return {
    enforceStorageLimit: (...args: any[]) => enforceStorageLimitMock(...args),
    isClusterAvailableOffline: (...args: any[]) => isClusterAvailableOfflineMock(...args),
    listOfflineClusters: async () => [],
    removeClusterOffline: async () => {},
    saveClusterOffline: (...args: any[]) => saveClusterOfflineMock(...args),
  };
});

vi.mock('@/lib/api/clustersClient', () => {
  return {
    getClusterDetailClient: async () => ({
      kind: 'ok' as const,
      cluster: {
        cluster_id: 'c1',
        canonical_title: 'Saved story',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        distinct_source_count: 1,
        evidence: {},
        topics: [],
        content_type_breakdown: {},
        takeaway: null,
        summary_intuition: null,
        summary_deep_dive: null,
        assumptions: [],
        limitations: [],
        what_could_change_this: [],
        confidence_band: null,
        method_badges: [],
        anti_hype_flags: [],
        takeaway_supporting_item_ids: [],
        summary_intuition_supporting_item_ids: [],
        summary_deep_dive_supporting_item_ids: [],
        glossary_entries: [],
        is_saved: true,
        is_watched: false,
      },
    }),
  };
});

describe('SavedPage (download)', () => {
  it('downloads a saved story for offline reading', async () => {
    const user = userEvent.setup();
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/saved',
      };
    });
    vi.mock('@/lib/hooks/useNetworkStatus', () => {
      return { useNetworkStatus: () => ({ isOnline: true }) };
    });
    saveClusterOfflineMock.mockClear();
    enforceStorageLimitMock.mockClear();

    server.use(
      http.get(`${API}/user`, () => {
        return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
      }),
      http.get(`${API}/user/saves`, () => {
        return HttpResponse.json(
          {
            saved: [
              {
                saved_at: new Date().toISOString(),
                cluster: {
                  cluster_id: 'c1',
                  canonical_title: 'Saved story',
                  updated_at: new Date().toISOString(),
                  distinct_source_count: 1,
                  top_topics: [],
                  content_type_badges: ['news'],
                  confidence_band: null,
                  takeaway: null,
                  anti_hype_flags: [],
                },
              },
            ],
          },
          { status: 200 }
        );
      })
    );

    const { SavedPage } = await import('./SavedPage');
    const { findByRole, findByText } = renderWithProviders(<SavedPage />);

    expect(await findByText('Saved story')).toBeInTheDocument();

    const offlineBtn = await findByRole('button', { name: /offline/i });
    await user.click(offlineBtn);

    expect(saveClusterOfflineMock).toHaveBeenCalled();
    expect(enforceStorageLimitMock).toHaveBeenCalled();
  });
});
