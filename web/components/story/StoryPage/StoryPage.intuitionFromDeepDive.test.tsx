import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StoryPage } from './StoryPage';
import { renderWithProviders } from '@/test/utils';

describe('StoryPage intuition fallback from deep-dive payload', () => {
  it('shows ELI20 toggle when eli20 exists inside summary_deep_dive JSON payload', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <StoryPage
        cluster={{
          cluster_id: '11111111-1111-1111-1111-111111111111',
          canonical_title: 'Safety paper',
          created_at: new Date('2026-02-06T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-06T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          evidence: {
            preprint: [
              {
                item_id: '21111111-1111-1111-1111-111111111111',
                title: 'Paper evidence',
                url: 'https://example.com/paper',
                published_at: null,
                source: { source_id: 's1', name: 'arXiv' },
                content_type: 'preprint',
              },
            ],
          },
          topics: [],
          content_type_breakdown: { preprint: 1 },
          takeaway: 'Simple takeaway.',
          summary_intuition: 'ELI5 explanation',
          summary_deep_dive: JSON.stringify({
            markdown: '## Deep dive\n\nTechnical details.',
            eli20: 'ELI20 explanation',
          }),
          assumptions: [],
          limitations: [],
          what_could_change_this: [],
          method_badges: [],
          anti_hype_flags: [],
          takeaway_supporting_item_ids: ['21111111-1111-1111-1111-111111111111'],
          summary_intuition_supporting_item_ids: ['21111111-1111-1111-1111-111111111111'],
          summary_deep_dive_supporting_item_ids: ['21111111-1111-1111-1111-111111111111'],
          glossary_entries: [],
          is_saved: null,
          is_watched: null,
        }}
      />
    );

    expect(screen.getByText('ELI20 explanation')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'ELI20' })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'ELI5' }));
    expect(screen.getByText('ELI5 explanation')).toBeInTheDocument();
  });

  it('does not render Deep Dive when payload has no markdown content', () => {
    renderWithProviders(
      <StoryPage
        cluster={{
          cluster_id: '12222222-1111-1111-1111-111111111111',
          canonical_title: 'Payload-only intuition story',
          created_at: new Date('2026-02-06T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-06T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          evidence: { preprint: [] },
          topics: [],
          content_type_breakdown: { preprint: 1 },
          takeaway: null,
          summary_intuition: null,
          summary_deep_dive: JSON.stringify({
            eli20: 'Payload ELI20 only',
          }),
          assumptions: [],
          limitations: [],
          what_could_change_this: [],
          method_badges: [],
          anti_hype_flags: [],
          takeaway_supporting_item_ids: [],
          summary_intuition_supporting_item_ids: [],
          summary_deep_dive_supporting_item_ids: [],
          glossary_entries: [],
          is_saved: null,
          is_watched: null,
        }}
      />
    );

    expect(screen.getByText('Payload ELI20 only')).toBeInTheDocument();
    expect(screen.queryByText('Deep Dive')).toBeNull();
  });
});
