import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/msw/server';
import { renderWithProviders } from '@/test/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

describe('NotificationSettingsPage', () => {
  it('shows parse errors for invalid JSON', async () => {
    const user = userEvent.setup();
    vi.mock('next/navigation', () => {
      return {
        useRouter: () => ({ replace: vi.fn() }),
        usePathname: () => '/settings/notifications',
      };
    });

    server.use(
      http.get(`${API}/user`, () => {
        return HttpResponse.json({ user: { user_id: 'u1', email: 'test@example.com' } }, { status: 200 });
      })
    );

    const { NotificationSettingsPage } = await import('./NotificationSettingsPage');
    const { findByLabelText, getByRole, findByText } = renderWithProviders(<NotificationSettingsPage />);

    const textbox = await findByLabelText(/notification_settings/i);
    await user.clear(textbox);
    fireEvent.change(textbox, { target: { value: '{not json' } });

    const save = getByRole('button', { name: /^save$/i });
    await user.click(save);

    expect(await findByText('Invalid JSON.')).toBeInTheDocument();
  });
});
