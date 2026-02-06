import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

const removeClusterOfflineMock = vi.fn(async () => {});

vi.mock('@/lib/offline/db', async () => {
  const mod = await vi.importActual<any>('@/lib/offline/db');
  return { ...mod, removeClusterOffline: (...args: any[]) => removeClusterOfflineMock(...args) };
});

describe('SavedPage (remove)', () => {
  it('removes from saves and deletes offline cache', async () => {
    const user = userEvent.setup();
    removeClusterOfflineMock.mockClear();

    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/saved',
      };
    });
    vi.mock('@/lib/hooks/useNetworkStatus', () => {
      return { useNetworkStatus: () => ({ isOnline: true }) };
    });

    let deleted: string | null = null;

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
      }),
      http.delete(`${API}/user/saves/c1`, () => {
        deleted = 'c1';
        return HttpResponse.json({ status: 'ok' }, { status: 200 });
      })
    );

    const { SavedPage } = await import('./SavedPage');
    const { findByText, findByRole } = renderWithProviders(<SavedPage />);

    expect(await findByText('Saved story')).toBeInTheDocument();

    await user.click(await findByRole('button', { name: /remove/i }));

    expect(deleted).toBe('c1');
    expect(removeClusterOfflineMock).toHaveBeenCalledWith('c1');
  });
});

