import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';

vi.mock('@/lib/api/user', async () => {
  const { ApiError } = await import('@/lib/api/errors');
  return {
    saveCluster: async () => {
      throw new ApiError(401, 'http_error', 'Unauthenticated', { detail: 'Unauthenticated' });
    },
    unsaveCluster: async () => ({ status: 'ok' }),
    watchCluster: async () => ({ status: 'ok' }),
    unwatchCluster: async () => ({ status: 'ok' }),
  };
});

vi.mock('@/lib/offline/db', () => {
  return {
    enforceStorageLimit: async () => {},
    removeClusterOffline: async () => {},
    saveClusterOffline: async () => {},
  };
});

describe('StoryActions (unauth)', () => {
  it('shows inline login hint on 401 without flipping saved state', async () => {
    const user = userEvent.setup();
    const { StoryActions } = await import('./StoryActions');

    const { findByText, getByRole } = renderWithProviders(
      <StoryActions clusterId="00000000-0000-0000-0000-000000000001" initial={{ saved: false, watched: false }} />
    );

    await user.click(getByRole('button', { name: /^save$/i }));
    expect(await findByText(/Login required/i)).toBeInTheDocument();
    expect(getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(getByRole('link', { name: /^log in$/i })).toHaveAttribute(
      'href',
      '/auth/login?redirect=%2F'
    );
  });
});
