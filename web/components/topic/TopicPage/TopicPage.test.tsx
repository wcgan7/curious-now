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
});
