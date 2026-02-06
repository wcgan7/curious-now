import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

describe('SettingsPage', () => {
  it('loads prefs and lets user change reading mode', async () => {
    const user = userEvent.setup();
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/settings',
      };
    });

    let patchedMode: string | null = null;

    server.use(
      http.get(`${API}/user`, () => {
        return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
      }),
      http.get(`${API}/user/prefs`, () => {
        return HttpResponse.json(
          {
            prefs: {
              reading_mode_default: 'deep',
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
        const body = (await request.json().catch(() => ({}))) as any;
        patchedMode = body.reading_mode_default || null;
        return HttpResponse.json(
          {
            prefs: {
              reading_mode_default: patchedMode || 'deep',
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
      })
    );

    const { SettingsPage } = await import('./SettingsPage');
    const { findByRole, getByRole } = renderWithProviders(<SettingsPage />);

    const deep = await findByRole('radio', { name: /Deep/i });
    expect(deep).toBeChecked();

    const intuition = getByRole('radio', { name: /Intuition/i });
    await user.click(intuition);
    expect(intuition).toBeChecked();

    const save = getByRole('button', { name: /^save$/i });
    expect(save).not.toBeDisabled();
    await user.click(save);

    expect(patchedMode).toBe('intuition');
  });
});
