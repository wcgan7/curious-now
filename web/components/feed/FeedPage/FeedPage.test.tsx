import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { getFeed } from '@/lib/api/feed';

import { FeedPage } from './FeedPage';

vi.mock('@/lib/api/feed', () => ({
  getFeed: vi.fn(),
}));

describe('FeedPage', () => {
  it('renders fallback notice when feed request fails', async () => {
    vi.mocked(getFeed).mockRejectedValueOnce(new Error('feed failed'));

    render(await FeedPage({ tab: 'latest' }));

    expect(
      screen.getByText("Couldn't load the feed right now. Please refresh in a moment.")
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Latest' })).toBeInTheDocument();
  });
});
