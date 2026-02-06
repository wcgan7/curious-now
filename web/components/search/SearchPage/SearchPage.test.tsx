import { describe, expect, it, vi } from 'vitest';
import { fireEvent } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils';
import { SearchPage } from './SearchPage';

vi.mock('next/navigation', () => {
  return {
    useRouter: () => ({ push: vi.fn() }),
    useSearchParams: () => new URLSearchParams('q=ai'),
  };
});

describe('SearchPage', () => {
  it('shows results for a query', async () => {
    const { findByText, getByPlaceholderText } = renderWithProviders(<SearchPage />);
    expect(await findByText('Artificial Intelligence')).toBeInTheDocument();
    expect(await findByText('AI does a thing')).toBeInTheDocument();

    const input = getByPlaceholderText('Search stories, topics…');
    fireEvent.change(input, { target: { value: 'battery' } });
    expect((input as HTMLInputElement).value).toBe('battery');
  });
});

