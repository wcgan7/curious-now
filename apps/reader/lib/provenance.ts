import type { SourceLink } from "@/lib/types";

/** How a piece of work was vetted, where that is established.
 *
 * "Peer reviewed" and "Preprint" are claims about vetting, so they are withheld
 * where nothing establishes them. That is narrower than it sounds: arXiv's feed
 * carries preprints and nothing else, so its default describes every item on
 * it. Only a feed known to carry several kinds — Nature sends research, news,
 * comment and book reviews down one URL — leaves an unmatched item
 * unclassified.
 *
 * Shared between the feed and the story page deliberately. The two showed
 * different things: a card said "Preprint" and the page a reader landed on from
 * search said nothing at all, so the same work was unreviewed in one place and
 * unmarked in the other.
 */
export const reviewLabels: Partial<Record<SourceLink["contentType"], string>> = {
  preprint: "Preprint",
  peer_reviewed: "Peer reviewed",
  report: "Report",
  dataset: "Dataset",
};

export const PAPER_TYPES: ReadonlyArray<SourceLink["contentType"]> = [
  "preprint",
  "peer_reviewed",
];

export function reviewBadge(source: SourceLink): string | undefined {
  if (source.contentTypeBasis === "feed_unmatched") {
    return undefined;
  }
  return reviewLabels[source.contentType];
}

/** The source whose vetting describes the story.
 *
 * A story's first item is usually the paper, but journalism about a paper puts
 * the article first — and it is the paper's review status a reader needs, not
 * the newspaper's.
 */
export function vettingSource(sources: SourceLink[]): SourceLink | undefined {
  return (
    sources.find(
      (source) =>
        PAPER_TYPES.includes(source.contentType) &&
        source.contentTypeBasis !== "feed_unmatched",
    ) ?? sources[0]
  );
}
