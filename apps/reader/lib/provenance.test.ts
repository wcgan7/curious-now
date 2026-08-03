import { describe, expect, it } from "vitest";

import { reviewBadge, vettingSource } from "@/lib/provenance";
import type { SourceLink } from "@/lib/types";

function source(over: Partial<SourceLink> = {}): SourceLink {
  return {
    sourceName: "arXiv",
    contentType: "preprint",
    contentTypeBasis: "source_pattern",
    ...over,
  } as SourceLink;
}

describe("reviewBadge", () => {
  it("names how the work was vetted", () => {
    expect(reviewBadge(source())).toBe("Preprint");
    expect(reviewBadge(source({ contentType: "peer_reviewed" }))).toBe(
      "Peer reviewed",
    );
  });

  it("withholds the claim when nothing establishes it", () => {
    // Nature sends research, news, comment and book reviews down one URL, so an
    // unmatched item there is not known to be reviewed.
    expect(
      reviewBadge(
        source({ contentType: "peer_reviewed", contentTypeBasis: "feed_unmatched" }),
      ),
    ).toBeUndefined();
  });

  it("keeps a feed default that describes every item on the feed", () => {
    // arXiv carries preprints and nothing else.
    expect(
      reviewBadge(source({ contentTypeBasis: "feed_default" })),
    ).toBe("Preprint");
  });

  it("says nothing about things that are not papers", () => {
    expect(reviewBadge(source({ contentType: "news" }))).toBeUndefined();
    expect(reviewBadge(source({ contentType: "blog" }))).toBeUndefined();
  });
});

describe("vettingSource", () => {
  it("prefers the paper over the article about it", () => {
    // A reader needs the paper's review status, not the newspaper's.
    const chosen = vettingSource([
      source({ sourceName: "BBC", contentType: "news" }),
      source({ sourceName: "Nature", contentType: "peer_reviewed" }),
    ]);

    expect(chosen?.sourceName).toBe("Nature");
  });

  it("ignores a paper whose type is not established", () => {
    const chosen = vettingSource([
      source({ sourceName: "BBC", contentType: "news" }),
      source({
        sourceName: "Nature",
        contentType: "peer_reviewed",
        contentTypeBasis: "feed_unmatched",
      }),
    ]);

    expect(chosen?.sourceName).toBe("BBC");
  });

  it("falls back to the first source when none is a paper", () => {
    expect(
      vettingSource([source({ sourceName: "BBC", contentType: "news" })])
        ?.sourceName,
    ).toBe("BBC");
  });

  it("handles a story with no sources", () => {
    expect(vettingSource([])).toBeUndefined();
  });
});
