import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

import { TopicPage } from './TopicPage';

describe('TopicPage', () => {
  it('renders nested topic fields and uses category-specific UI behavior', () => {
    const { getByRole, getByText, queryByRole } = render(
      <TopicPage
        detail={{
          topic: {
            topic_id: '00000000-0000-0000-0000-000000000010',
            name: 'Artificial Intelligence',
            description_short: 'ML research and applications',
            topic_type: 'category',
            parent_topic_id: null,
          },
          latest_clusters: [],
          trending_clusters: [],
        }}
      />
    );

    expect(getByRole('heading', { level: 1, name: 'Artificial Intelligence' })).toBeInTheDocument();
    expect(getByText('ML research and applications')).toBeInTheDocument();
    expect(getByRole('link', { name: 'Search related' })).toHaveAttribute(
      'href',
      '/search?q=Artificial%20Intelligence'
    );
    expect(queryByRole('link', { name: 'Lineage' })).not.toBeInTheDocument();
  });

  it('deduplicates clusters by cluster_id before rendering lists', () => {
    const { getByText, queryByText } = render(
      <TopicPage
        detail={{
          topic: {
            topic_id: '00000000-0000-0000-0000-000000000010',
            name: 'Artificial Intelligence',
            description_short: 'ML research and applications',
            topic_type: 'category',
            parent_topic_id: null,
          },
          latest_clusters: [
            {
              cluster_id: '26d22e55-6e10-4760-85de-83f750a66861',
              canonical_title: 'First title',
              updated_at: '2026-02-12T00:00:00Z',
              distinct_source_count: 1,
              top_topics: [],
              content_type_badges: [],
            } as any,
            {
              cluster_id: '26d22e55-6e10-4760-85de-83f750a66861',
              canonical_title: 'Duplicate title should not render',
              updated_at: '2026-02-12T00:00:00Z',
              distinct_source_count: 1,
              top_topics: [],
              content_type_badges: [],
            } as any,
          ],
          trending_clusters: [],
        }}
      />
    );

    expect(getByText('First title')).toBeInTheDocument();
    expect(queryByText('Duplicate title should not render')).not.toBeInTheDocument();
  });
});
