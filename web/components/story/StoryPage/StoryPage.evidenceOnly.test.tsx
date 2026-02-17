import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StoryPage } from './StoryPage';
import { renderWithProviders } from '@/test/utils';

describe('StoryPage (evidence-only)', () => {
  it('renders even when understanding fields are null', () => {
    const { getByRole, getByText, queryByText } = renderWithProviders(
      <StoryPage
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000001',
          canonical_title: 'Evidence-only story',
          created_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          evidence: {
            news: [
              {
                item_id: '00000000-0000-0000-0000-000000000101',
                title: 'Evidence item title',
                url: 'https://example.com',
                published_at: null,
                source: { source_id: 's1', name: 'Example' },
                content_type: 'news',
              },
            ],
          },
          topics: [],
          content_type_breakdown: { news: 1 },
          categories: [
            {
              category_id: 'c1',
              name: 'Artificial Intelligence',
              score: 0.91,
            },
          ],
          takeaway: null,
          summary_intuition: null,
          summary_deep_dive: null,
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

    expect(getByText('Evidence-only story')).toBeInTheDocument();
    expect(getByText('Artificial Intelligence')).toBeInTheDocument();
    expect(getByText('Evidence item title')).toBeInTheDocument();
    expect(getByRole('link', { name: /read the article/i })).toHaveAttribute(
      'href',
      'https://example.com'
    );
    expect(queryByText('Quick Explainer')).toBeNull();
    expect(queryByText('Deep Dive')).toBeNull();
    expect(queryByText('View updates')).toBeNull();
  });

  it('shows updates link only when hasUpdates is true', () => {
    const { getByText } = renderWithProviders(
      <StoryPage
        hasUpdates
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000002',
          canonical_title: 'Story with updates',
          created_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          evidence: { news: [] },
          topics: [],
          content_type_breakdown: {},
          takeaway: null,
          summary_intuition: null,
          summary_deep_dive: null,
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

    expect(getByText('View updates')).toBeInTheDocument();
  });

  it('hides direct source link when story has multiple sources', () => {
    const { queryByRole } = renderWithProviders(
      <StoryPage
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000003',
          canonical_title: 'Multi-source story',
          created_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 2,
          evidence: {
            news: [
              {
                item_id: '00000000-0000-0000-0000-000000000301',
                title: 'Story A',
                url: 'https://example.com/a',
                published_at: null,
                source: { source_id: 's1', name: 'Example A' },
                content_type: 'news',
              },
            ],
            blog: [
              {
                item_id: '00000000-0000-0000-0000-000000000302',
                title: 'Story B',
                url: 'https://example.com/b',
                published_at: null,
                source: { source_id: 's2', name: 'Example B' },
                content_type: 'blog',
              },
            ],
          },
          topics: [],
          content_type_breakdown: { news: 1, blog: 1 },
          takeaway: null,
          summary_intuition: null,
          summary_deep_dive: null,
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

    expect(queryByRole('link', { name: /read the article/i })).toBeNull();
  });

  it('opens and closes a modal when the story image is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <StoryPage
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000004',
          canonical_title: 'Story with image',
          featured_image_url: 'https://example.com/story-image.jpg',
          created_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          evidence: { news: [] },
          topics: [],
          content_type_breakdown: {},
          takeaway: null,
          summary_intuition: null,
          summary_deep_dive: null,
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

    expect(screen.queryByRole('dialog', { name: /story with image/i })).toBeNull();
    await user.click(screen.getByRole('button', { name: /open story image/i }));
    expect(screen.getByRole('dialog', { name: /story with image/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByRole('dialog', { name: /story with image/i })).toBeNull();
  });
});
