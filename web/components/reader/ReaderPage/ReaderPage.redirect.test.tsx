import { describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils';

let replaceMock = vi.fn();

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ replace: replaceMock }),
    useSearchParams: () => new URLSearchParams('id=from-id'),
  };
});

vi.mock('@/lib/hooks/useNetworkStatus', () => {
  return { useNetworkStatus: () => ({ isOnline: true }) };
});

vi.mock('@/lib/api/clustersClient', () => {
  return {
    getClusterDetailClient: async () => ({ kind: 'redirect' as const, toId: 'to-id' }),
  };
});

vi.mock('@/lib/offline/db', () => {
  return {
    getClusterOffline: async () => null,
    saveClusterOffline: async () => {},
  };
});

describe('ReaderPage (redirect)', () => {
  it('navigates to canonical id when API returns redirect', async () => {
    replaceMock = vi.fn();

    const { ReaderPage } = await import('./ReaderPage');
    renderWithProviders(<ReaderPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/reader?id=to-id');
    });
  });
});
