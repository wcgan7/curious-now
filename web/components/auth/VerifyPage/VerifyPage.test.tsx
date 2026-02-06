import { describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils';

let replaceMock = vi.fn();

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ replace: replaceMock }),
    useSearchParams: () => new URLSearchParams('token=tok_123&redirect=%2Fsaved'),
  };
});

describe('VerifyPage', () => {
  it('verifies token then redirects to redirect param', async () => {
    replaceMock = vi.fn();

    const { VerifyPage } = await import('./VerifyPage');
    renderWithProviders(<VerifyPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/saved');
    });
  });
});
