import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ClusterCard } from './ClusterCard';

describe('ClusterCard', () => {
  it('does not render nested anchors', () => {
    const { container } = render(
      <ClusterCard
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000001',
          canonical_title: 'Test title',
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 2,
          top_topics: [],
          content_type_badges: ['news'],
          takeaway: null,
          anti_hype_flags: [],
        }}
      />
    );

    const anchors = container.querySelectorAll('a');
    expect(anchors.length).toBe(1);
    expect(anchors[0].querySelector('a')).toBeNull();
    expect(anchors[0].getAttribute('href')).toBe('/story/00000000-0000-0000-0000-000000000001');
  });

  it('renders source type chips instead of anti-hype flags', () => {
    render(
      <ClusterCard
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000002',
          canonical_title: 'Source type card',
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          top_topics: [],
          content_type_badges: ['preprint', 'news'],
          takeaway: null,
          anti_hype_flags: ['single_source', 'preprint_not_peer_reviewed'],
        }}
      />
    );

    expect(screen.getByLabelText('Source types')).toBeInTheDocument();
    expect(screen.getByText('preprint')).toBeInTheDocument();
    expect(screen.getByText('news')).toBeInTheDocument();
    expect(screen.queryByText('single source')).toBeNull();
    expect(screen.queryByText('preprint not peer reviewed')).toBeNull();
  });

  it('prefers focused category chip when provided', () => {
    render(
      <ClusterCard
        focusCategory={{
          categoryId: 'cat-ai',
          name: 'Artificial Intelligence',
        }}
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000004',
          canonical_title: 'Focused category card',
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          top_topics: [
            {
              topic_id: 'topic-1',
              name: 'Molecular & Cell Biology',
              score: 0.8,
            },
          ],
          top_categories: [
            {
              category_id: 'cat-materials',
              name: 'Materials & Engineering',
              score: 0.9,
            },
            {
              category_id: 'cat-ai',
              name: 'Artificial Intelligence',
              score: 0.7,
            },
          ],
          content_type_badges: [],
          takeaway: null,
          anti_hype_flags: [],
        }}
      />
    );

    expect(screen.getByText('Artificial Intelligence')).toBeInTheDocument();
    expect(screen.queryByText('Materials & Engineering')).toBeNull();
  });

  it('shows In Focus chip when cluster is marked in focus', () => {
    render(
      <ClusterCard
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000005',
          canonical_title: 'In focus card',
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          top_topics: [],
          content_type_badges: [],
          takeaway: null,
          anti_hype_flags: [],
          in_focus_label: true,
        }}
      />
    );

    expect(screen.getByText('In Focus')).toBeInTheDocument();
  });

  it('does not show In Focus chip when cluster is not marked in focus', () => {
    render(
      <ClusterCard
        cluster={{
          cluster_id: '00000000-0000-0000-0000-000000000006',
          canonical_title: 'Standard card',
          updated_at: new Date('2026-02-05T00:00:00Z').toISOString(),
          distinct_source_count: 1,
          top_topics: [],
          content_type_badges: [],
          takeaway: null,
          anti_hype_flags: [],
          in_focus_label: false,
        }}
      />
    );

    expect(screen.queryByText('In Focus')).toBeNull();
  });
});
