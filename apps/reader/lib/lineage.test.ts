import { describe, expect, it } from "vitest";

import {
  citedWorkUrl,
  groupLineage,
  orderLineage,
} from "@/lib/lineage";
import type { LineageEdge } from "@/lib/types";

function edge(over: Partial<LineageEdge> = {}): LineageEdge {
  return {
    relation: "applies",
    title: "A prior work",
    doi: null,
    arxivId: null,
    quote: "We use the estimator of Smith et al.",
    ...over,
  };
}

describe("orderLineage", () => {
  it("leads with what tells a reader most, not with what is commonest", () => {
    // 344 of 454 edges in this corpus are "applies" and 14 are "contradicts".
    // Ordering by frequency would bury exactly the ones worth reading.
    const ordered = orderLineage([
      edge({ relation: "applies", title: "d" }),
      edge({ relation: "replicates", title: "c" }),
      edge({ relation: "extends", title: "b" }),
      edge({ relation: "contradicts", title: "a" }),
    ]);

    expect(ordered.map((e) => e.relation)).toEqual([
      "contradicts",
      "extends",
      "replicates",
      "applies",
    ]);
  });

  it("is stable for equal relations", () => {
    const ordered = orderLineage([
      edge({ title: "Beta" }),
      edge({ title: "Alpha" }),
    ]);

    expect(ordered.map((e) => e.title)).toEqual(["Alpha", "Beta"]);
  });

  it("does not mutate its input", () => {
    const input = [edge({ relation: "applies" }), edge({ relation: "contradicts" })];
    orderLineage(input);

    expect(input[0].relation).toBe("applies");
  });
});

describe("groupLineage", () => {
  it("treats one sentence about three works as one statement", () => {
    // "(Laland, 2004; Rendell et al., 2011; Muthukrishna et al., 2016) similarly
    // cannot accommodate the behavior we see here" is one claim, and repeating
    // it once per work reads as a bug rather than as evidence.
    const shared = "Heuristic accounts similarly cannot accommodate this.";
    const grouped = groupLineage([
      edge({ relation: "contradicts", title: "Laland", quote: shared }),
      edge({ relation: "contradicts", title: "Rendell", quote: shared }),
      edge({ relation: "contradicts", title: "Muthukrishna", quote: shared }),
    ]);

    expect(grouped).toHaveLength(1);
    expect(grouped[0].works.map((w) => w.title)).toEqual([
      "Laland",
      "Muthukrishna",
      "Rendell",
    ]);
  });

  it("keeps the same work separate when the paper said different things", () => {
    const grouped = groupLineage([
      edge({ relation: "applies", title: "X", quote: "We use X." }),
      edge({ relation: "extends", title: "X", quote: "We go beyond X." }),
    ]);

    expect(grouped).toHaveLength(2);
  });

  it("does not merge across relations even on an identical sentence", () => {
    const grouped = groupLineage([
      edge({ relation: "applies", title: "A", quote: "same" }),
      edge({ relation: "extends", title: "B", quote: "same" }),
    ]);

    expect(grouped).toHaveLength(2);
  });

  it("preserves the informativeness order across groups", () => {
    const grouped = groupLineage([
      edge({ relation: "applies", title: "A", quote: "a" }),
      edge({ relation: "contradicts", title: "B", quote: "b" }),
    ]);

    expect(grouped[0].relation).toBe("contradicts");
  });

  it("returns nothing for a paper that cites nothing typed", () => {
    expect(groupLineage([])).toEqual([]);
  });
});

describe("citedWorkUrl", () => {
  it("prefers the DOI", () => {
    expect(citedWorkUrl(edge({ doi: "10.1/x", arxivId: "2401.00001" }))).toBe(
      "https://doi.org/10.1/x",
    );
  });

  it("falls back to arXiv", () => {
    expect(citedWorkUrl(edge({ arxivId: "2401.00001" }))).toBe(
      "https://arxiv.org/abs/2401.00001",
    );
  });

  it("offers no link rather than a search that might not find it", () => {
    expect(citedWorkUrl(edge())).toBeNull();
  });
});

