import { describe, expect, it, vi } from 'vitest';
import { fireEvent } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils';

describe('LoginPage', () => {
  it('validates email and shows sent state', async () => {
    vi.mock('next/navigation', () => {
      return {
        useSearchParams: () => new URLSearchParams('redirect=%2Fsaved'),
      };
    });

    const { LoginPage } = await import('./LoginPage');
    const { findByText, getByLabelText, getByRole } = renderWithProviders(<LoginPage />);

    const submit = getByRole('button', { name: /send magic link/i });
    expect(submit).toBeDisabled();

    const input = getByLabelText('Email');
    fireEvent.change(input, { target: { value: 'not-an-email' } });
    expect(await findByText('Enter a valid email address')).toBeInTheDocument();
    expect(submit).toBeDisabled();

    fireEvent.change(input, { target: { value: 'test@example.com' } });
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);
    expect(await findByText(/Check your email/i)).toBeInTheDocument();
  });
});

