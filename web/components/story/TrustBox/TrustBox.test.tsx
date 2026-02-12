import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TrustBox } from './TrustBox';

describe('TrustBox', () => {
  it('does not render when there is nothing to show', () => {
    const { container } = render(
      <TrustBox
        contentTypeBreakdown={{}}
        distinctSourceCount={1}
        methodBadges={[]}
        antiHypeFlags={[]}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('does not render when single_source is the only note', () => {
    const { container } = render(
      <TrustBox
        contentTypeBreakdown={{ news: 1 }}
        distinctSourceCount={1}
        methodBadges={[]}
        antiHypeFlags={['single_source']}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders for multi-source clusters', () => {
    render(
      <TrustBox
        contentTypeBreakdown={{ news: 2 }}
        distinctSourceCount={2}
        methodBadges={[]}
        antiHypeFlags={[]}
      />
    );

    expect(screen.getByText('Source summary')).toBeInTheDocument();
    expect(screen.getByText('Independent sources')).toBeInTheDocument();
  });

  it('renders non-single_source notes for single-source clusters', () => {
    render(
      <TrustBox
        contentTypeBreakdown={{ preprint: 1 }}
        distinctSourceCount={1}
        methodBadges={[]}
        antiHypeFlags={['single_source', 'preprint_not_peer_reviewed']}
      />
    );

    expect(screen.getByText('preprint not peer reviewed')).toBeInTheDocument();
    expect(screen.queryByText('single source')).not.toBeInTheDocument();
  });
});
