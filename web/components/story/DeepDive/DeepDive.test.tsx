import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

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
    const { container, getByText } = render(
      <DeepDive
        value={`## Methods

The team used a *controlled* setup with **3 groups**.

- Small sample size
- Results need replication

Read the protocol at [source](https://example.com/protocol).`}
      />
    );

    expect(getByText('Methods')).toBeInTheDocument();
    expect(getByText('Small sample size')).toBeInTheDocument();
    expect(getByText('Results need replication')).toBeInTheDocument();
    expect(getByText('source')).toHaveAttribute('href', 'https://example.com/protocol');
    expect(container.querySelector('em')?.textContent).toBe('controlled');
    expect(container.querySelector('strong')?.textContent).toBe('3 groups');
  });

  it('preserves nested markdown list hierarchy', () => {
    const { getByText } = render(
      <DeepDive
        value={`## Notes

- Parent
  - Child A
  - Child B
- Parent 2`}
      />
    );

    const parent = getByText('Parent');
    const childA = getByText('Child A');
    expect(parent).toBeInTheDocument();
    expect(childA).toBeInTheDocument();

    const lists = screen.getAllByRole('list');
    expect(lists.length).toBeGreaterThanOrEqual(2);
    expect(lists[0]).toContainElement(lists[1]);
  });

  it('keeps indented continuation text inside the parent bullet', () => {
    const { container, getByText } = render(
      <DeepDive
        value={`## Interpretation

- The reported gains are consistent with the claim that explicitly handling:
  - network-level structure, and
  - stimulus/brain timescale alignment
  improves causal forward prediction of naturalistic brain dynamics.`}
      />
    );

    expect(getByText(/The reported gains are consistent/i)).toBeInTheDocument();
    expect(getByText(/improves causal forward prediction/i)).toBeInTheDocument();
    expect(container.querySelectorAll('p').length).toBe(0);
    const html = container.innerHTML;
    expect(html.indexOf('stimulus/brain timescale alignment')).toBeLessThan(
      html.indexOf('improves causal forward prediction of naturalistic brain dynamics')
    );
  });
});
