import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

const unfollowTopicMock = vi.fn(async () => ({ status: 'ok' }));
const followTopicMock = vi.fn(async () => ({ status: 'ok' }));

vi.mock('@/lib/api/user', async () => {
  const mod = await vi.importActual<any>('@/lib/api/user');
  return { ...mod, unfollowTopic: (...args: any[]) => unfollowTopicMock(...args), followTopic: (...args: any[]) => followTopicMock(...args) };
});

describe('FollowButton', () => {
  it('shows Following when prefs include topic id, and can unfollow', async () => {
    const user = userEvent.setup();
    unfollowTopicMock.mockClear();

    server.use(
      http.get(`${API}/user/prefs`, () => {
        return HttpResponse.json(
          {
            prefs: {
              reading_mode_default: 'intuition',
              followed_topic_ids: ['t1'],
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

    const { FollowButton } = await import('./FollowButton');
    const { findByRole } = renderWithProviders(<FollowButton topicId="t1" initialIsFollowed={null} />);

    const btn = await findByRole('button', { name: /following/i });
    await user.click(btn);

    expect(unfollowTopicMock).toHaveBeenCalledWith('t1');
  });
});
