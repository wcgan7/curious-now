import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

import { DeepDive } from './DeepDive';

describe('DeepDive', () => {
  it('renders structured sections when given JSON', () => {
    const { getByText, queryByText } = render(
      <DeepDive
        value={JSON.stringify({
          what_happened: 'A thing happened.',
          why_it_matters: 'It matters.',
          background: 'Some context.',
          limitations: ['Limit 1', 'Limit 2'],
          whats_next: 'Next steps.',
          related_concepts: ['IoT', 'CPS'],
        })}
      />
    );

    expect(getByText('What happened')).toBeInTheDocument();
    expect(getByText('A thing happened.')).toBeInTheDocument();
    expect(getByText('Limitations')).toBeInTheDocument();
    expect(getByText('Limit 1')).toBeInTheDocument();
    expect(getByText('Related concepts')).toBeInTheDocument();
    expect(getByText('IoT')).toBeInTheDocument();

    expect(queryByText(/what_happened/i)).toBeNull();
  });

  it('renders markdown deep dive content', () => {
    const { getByText } = render(
      <DeepDive
        value={`## Methods

The team used a controlled setup with 3 groups.

- Small sample size
- Results need replication

Read the protocol at [source](https://example.com/protocol).`}
      />
    );

    expect(getByText('Methods')).toBeInTheDocument();
    expect(getByText('Small sample size')).toBeInTheDocument();
    expect(getByText('Results need replication')).toBeInTheDocument();
    expect(getByText('source')).toHaveAttribute('href', 'https://example.com/protocol');
  });
});
