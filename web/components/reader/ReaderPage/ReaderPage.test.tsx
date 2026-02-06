import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils';

describe('ReaderPage', () => {
  it('shows offline missing state when offline cache is empty', async () => {
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        useSearchParams: () => new URLSearchParams('id=00000000-0000-0000-0000-000000000999'),
      };
    });
    vi.mock('@/lib/hooks/useNetworkStatus', () => {
      return { useNetworkStatus: () => ({ isOnline: false }) };
    });
    vi.mock('@/lib/offline/db', () => {
      return {
        getClusterOffline: async () => null,
        saveClusterOffline: async () => {},
      };
    });

    const { ReaderPage } = await import('./ReaderPage');
    const { findByText } = renderWithProviders(<ReaderPage />);

    expect(await findByText(/isn't available offline/i)).toBeInTheDocument();
  });
});

