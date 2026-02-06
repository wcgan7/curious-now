import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

let replaceMock = vi.fn();

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ replace: replaceMock }),
    useSearchParams: () => new URLSearchParams('token=bad&redirect=%2F'),
  };
});

describe('VerifyPage (error)', () => {
  it('shows invalid/expired message on 400', async () => {
    replaceMock = vi.fn();
    server.use(
      http.post(`${API}/auth/magic_link/verify`, () => {
        return HttpResponse.json({ detail: 'Invalid token' }, { status: 400 });
      })
    );

    const { VerifyPage } = await import('./VerifyPage');
    const { findByText } = renderWithProviders(<VerifyPage />);

    expect(await findByText(/invalid or expired/i)).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

