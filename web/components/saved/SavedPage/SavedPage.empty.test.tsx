import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

describe('SavedPage (empty)', () => {
  it('shows empty state when no saved stories', async () => {
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/saved',
      };
    });

    server.use(
      http.get(`${API}/user`, () => {
        return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
      }),
      http.get(`${API}/user/saves`, () => {
        return HttpResponse.json({ saved: [] }, { status: 200 });
      })
    );

    const { SavedPage } = await import('./SavedPage');
    const { findByText } = renderWithProviders(<SavedPage />);

    expect(await findByText(/No saved stories yet/i)).toBeInTheDocument();
  });
});

