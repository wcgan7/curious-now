import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

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
          confidence_band: null,
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
});

