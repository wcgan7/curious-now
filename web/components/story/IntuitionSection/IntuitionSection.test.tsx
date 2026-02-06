import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { IntuitionSection } from './IntuitionSection';

describe('IntuitionSection', () => {
  const evidence = {
    news: [
      {
        item_id: 'item-1',
        title: 'Evidence 1',
        url: 'https://example.com/1',
        published_at: '2026-02-06T00:00:00Z',
        source: { source_id: 's1', name: 'Source 1' },
        content_type: 'news',
      },
    ],
  };

  it('toggles between ELI5 and ELI20', async () => {
    const user = userEvent.setup();

    render(
      <IntuitionSection
        eli5="Simple explanation"
        eli20="Technical explanation"
        evidence={evidence}
        supportingItemIdsEli5={['item-1']}
        supportingItemIdsEli20={['item-1']}
      />
    );

    expect(screen.getByText('Simple explanation')).toBeInTheDocument();
    expect(screen.queryByText('Technical explanation')).toBeNull();

    await user.click(screen.getByRole('tab', { name: 'ELI20' }));

    expect(screen.getByText('Technical explanation')).toBeInTheDocument();
    expect(screen.queryByText('Simple explanation')).toBeNull();
  });

  it('shows a single label if only one mode exists', () => {
    render(<IntuitionSection eli20="Only technical" evidence={evidence} />);
    expect(screen.getByText('ELI20')).toBeInTheDocument();
    expect(screen.getByText('Only technical')).toBeInTheDocument();
  });
});
