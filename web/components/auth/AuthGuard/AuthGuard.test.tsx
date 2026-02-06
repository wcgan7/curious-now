import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils';
import { AuthGuard } from './AuthGuard';

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ replace: vi.fn() }),
    usePathname: () => '/saved',
  };
});

describe('AuthGuard', () => {
  it('renders a login-required fallback when unauthenticated', async () => {
    const { findByText } = renderWithProviders(
      <AuthGuard>
        <div>Secret</div>
      </AuthGuard>
    );

    expect(await findByText('Login required')).toBeInTheDocument();
  });
});

