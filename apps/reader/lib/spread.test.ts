import { describe, expect, it } from "vitest";

import { mixFormats, spreadSources } from "@/lib/spread";
import type { FeedStory } from "@/lib/types";

function story(id: string, sourceName: string): FeedStory {
  return {
    id,
    title: id,
    publishedAt: "2026-08-01T00:00:00.000Z",
    sources: sourceName
      ? ([{ sourceName }] as unknown as FeedStory["sources"])
      : [],
  };
}

describe("spreadSources", () => {
  it("deals one story per publisher in turn", () => {
    const spread = spreadSources([
      story("a1", "arXiv"),
      story("a2", "arXiv"),
      story("a3", "arXiv"),
      story("n1", "Nature"),
      story("e1", "eLife"),
    ]);

    expect(spread.map((s) => s.id)).toEqual(["a1", "n1", "e1", "a2", "a3"]);
  });

  it("keeps the best-ranked story first", () => {
    const spread = spreadSources([story("n1", "Nature"), story("a1", "arXiv")]);

    expect(spread[0].id).toBe("n1");
  });

  it("loses nothing and invents nothing", () => {
    const input = [
      story("a1", "arXiv"),
      story("a2", "arXiv"),
      story("n1", "Nature"),
    ];

    const spread = spreadSources(input);

    expect(spread).toHaveLength(input.length);
    expect(new Set(spread.map((s) => s.id))).toEqual(
      new Set(input.map((s) => s.id)),
    );
  });

  it("breaks up a bulk drop from one publisher", () => {
    // arXiv publishes daily in bulk; the real first page was 16 of 20 from it.
    const input = [
      ...Array.from({ length: 8 }, (_, i) => story(`a${i}`, "arXiv")),
      story("n1", "Nature"),
      story("e1", "eLife"),
    ];

    const spread = spreadSources(input);
    const firstThree = spread.slice(0, 3).map((s) => s.sources[0].sourceName);

    expect(new Set(firstThree).size).toBe(3);
  });

  it("handles a story with no source without splitting each into its own run", () => {
    const spread = spreadSources([
      story("x1", ""),
      story("x2", ""),
      story("n1", "Nature"),
    ]);

    expect(spread.map((s) => s.id)).toEqual(["x1", "n1", "x2"]);
  });

  it("returns an empty page unchanged", () => {
    expect(spreadSources([])).toEqual([]);
  });
});

describe("mixFormats", () => {
  it("places one accessible story after every two technical stories", () => {
    expect(
      mixFormats(["t1", "t2", "t3", "t4"], ["n1", "n2"]),
    ).toEqual(["t1", "t2", "n1", "t3", "t4", "n2"]);
  });

  it("preserves each lane's ranking", () => {
    const mixed = mixFormats(["t1", "t2", "t3"], ["n1", "n2", "n3"]);

    expect(mixed.filter((value) => value.startsWith("t"))).toEqual([
      "t1",
      "t2",
      "t3",
    ]);
    expect(mixed.filter((value) => value.startsWith("n"))).toEqual([
      "n1",
      "n2",
      "n3",
    ]);
  });

  it("fills from the remaining lane when one is exhausted", () => {
    expect(mixFormats(["t1"], ["n1", "n2", "n3"])).toEqual([
      "t1",
      "n1",
      "n2",
      "n3",
    ]);
    expect(mixFormats(["t1", "t2"], [])).toEqual(["t1", "t2"]);
  });
});
