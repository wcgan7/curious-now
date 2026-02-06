import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils';

describe('SavedPage (offline)', () => {
  it('shows offline list when offline', async () => {
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/saved',
      };
    });
    vi.mock('@/lib/hooks/useNetworkStatus', () => {
      return { useNetworkStatus: () => ({ isOnline: false }) };
    });
    vi.mock('@/lib/offline/db', () => {
      return {
        listOfflineClusters: async () => [
          {
            cluster_id: '00000000-0000-0000-0000-000000000123',
            canonical_title: 'Offline story',
            saved_at: Date.now(),
          },
        ],
        removeClusterOffline: async () => {},
        enforceStorageLimit: async () => {},
        isClusterAvailableOffline: async () => true,
        saveClusterOffline: async () => {},
      };
    });

    const { SavedPage } = await import('./SavedPage');
    const { findByText, getByRole } = renderWithProviders(<SavedPage />);

    expect(await findByText(/You're offline/i)).toBeInTheDocument();
    expect(await findByText('Offline story')).toBeInTheDocument();

    const link = getByRole('link', { name: 'Offline story' });
    expect(link.getAttribute('href')).toBe('/reader?id=00000000-0000-0000-0000-000000000123');
  });
});

