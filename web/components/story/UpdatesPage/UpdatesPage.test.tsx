import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

import { UpdatesPage } from './UpdatesPage';

describe('UpdatesPage', () => {
  it('renders update entries', () => {
    const { getByText } = render(
      <UpdatesPage
        clusterId="c1"
        updates={{
          cluster_id: 'c1',
          updates: [
            {
              created_at: new Date('2026-02-05T00:00:00Z').toISOString(),
              change_type: 'refinement',
              summary: 'Refined the explanation',
              supporting_item_ids: [],
              diff: null,
            },
            {
              created_at: new Date('2026-02-06T00:00:00Z').toISOString(),
              change_type: 'new_evidence',
              summary: 'Added a new paper',
              supporting_item_ids: ['i1'],
            },
          ],
        }}
      />
    );

    expect(getByText('Refined the explanation')).toBeInTheDocument();
    expect(getByText('Added a new paper')).toBeInTheDocument();
    expect(getByText('refinement')).toBeInTheDocument();
    expect(getByText('new_evidence')).toBeInTheDocument();
  });
});

