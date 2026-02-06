import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { renderWithProviders } from '@/test/utils';
import { server } from '@/test/msw/server';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

const unblockSourceMock = vi.fn(async () => ({ status: 'ok' }));

vi.mock('@/lib/api/user', async () => {
  const mod = await vi.importActual<any>('@/lib/api/user');
  return { ...mod, unblockSource: (...args: any[]) => unblockSourceMock(...args) };
});

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ replace: vi.fn() }),
    usePathname: () => '/settings/sources',
  };
});

describe('BlockedSourcesPage', () => {
  it('renders blocked sources and can unblock', async () => {
    const user = userEvent.setup();
    unblockSourceMock.mockClear();

    server.use(
      http.get(`${API}/user`, () => {
        return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
      }),
      http.get(`${API}/user/prefs`, () => {
        return HttpResponse.json(
          {
            prefs: {
              reading_mode_default: 'intuition',
              followed_topic_ids: [],
              followed_entity_ids: [],
              blocked_source_ids: ['s1'],
              saved_cluster_ids: [],
              hidden_cluster_ids: [],
              notification_settings: {},
            },
          },
          { status: 200 }
        );
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
              {
                source: {
                  source_id: 's2',
                  name: 'Other Source',
                  homepage_url: null,
                  source_type: 'journal',
                  reliability_tier: null,
                  active: true,
                },
                feeds: [],
              },
            ],
          },
          { status: 200 }
        );
      })
    );

    const { BlockedSourcesPage } = await import('./BlockedSourcesPage');
    const { findByText, findByRole, queryByText } = renderWithProviders(<BlockedSourcesPage />);

    expect(await findByText('Example Source')).toBeInTheDocument();
    expect(queryByText('Other Source')).toBeNull();

    await user.click(await findByRole('button', { name: /unblock/i }));
    expect(unblockSourceMock).toHaveBeenCalledWith('s1');
  });
});

