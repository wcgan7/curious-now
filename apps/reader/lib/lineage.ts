import type { LineageEdge } from "@/lib/types";

/** Relations in the order they inform a reader, not alphabetically or by count.
 *
 * A paper disagreeing with another tells you the most and is the rarest — 14 of
 * 454 edges in this corpus. Reusing a method tells you the least and is 344 of
 * them. Sorting by frequency would bury exactly the edges worth reading.
 */
const INFORMATIVENESS: Record<LineageEdge["relation"], number> = {
  contradicts: 0,
  extends: 1,
  replicates: 2,
  applies: 3,
};

/** What the relation means, in the paper's own voice rather than a schema's. */
export const relationVerb: Record<LineageEdge["relation"], string> = {
  contradicts: "Argues against",
  extends: "Builds on",
  replicates: "Confirms",
  applies: "Uses",
};

export function orderLineage(edges: LineageEdge[]): LineageEdge[] {
  return [...edges].sort(
    (a, b) =>
      INFORMATIVENESS[a.relation] - INFORMATIVENESS[b.relation] ||
      a.title.localeCompare(b.title),
  );
}

/** One statement the paper made, and every work it made it about.
 *
 * Papers cite several works in a single sentence — "(Laland, 2004; Rendell et
 * al., 2011; Muthukrishna et al., 2016) similarly cannot accommodate the
 * behavior we see here" is one claim about three works, not three claims. 187
 * quotes in this corpus are shared that way, and repeating the sentence once
 * per work reads as a bug rather than as evidence.
 */
export interface LineageStatement {
  relation: LineageEdge["relation"];
  quote: string;
  works: LineageEdge[];
}

export function groupLineage(edges: LineageEdge[]): LineageStatement[] {
  const groups = new Map<string, LineageStatement>();
  for (const edge of orderLineage(edges)) {
    const key = `${edge.relation}\u0000${edge.quote}`;
    const existing = groups.get(key);
    if (existing) {
      existing.works.push(edge);
    } else {
      groups.set(key, {
        relation: edge.relation,
        quote: edge.quote,
        works: [edge],
      });
    }
  }
  return [...groups.values()];
}

/** Where to read the cited work. Never a search — a link that might not find it
 *  is worse than no link. */
export function citedWorkUrl(edge: LineageEdge): string | null {
  if (edge.doi) {
    return `https://doi.org/${edge.doi}`;
  }
  if (edge.arxivId) {
    return `https://arxiv.org/abs/${edge.arxivId}`;
  }
  return null;
}
