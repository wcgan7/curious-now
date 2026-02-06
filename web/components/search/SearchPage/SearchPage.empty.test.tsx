import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils';

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ push: vi.fn() }),
    useSearchParams: () => new URLSearchParams('q=zzzzzz'),
  };
});

describe('SearchPage (empty)', () => {
  it('shows empty state when no results', async () => {
    const { SearchPage } = await import('./SearchPage');
    const { findByText } = renderWithProviders(<SearchPage />);

    expect(await findByText(/No results for/i)).toBeInTheDocument();
  });
});

