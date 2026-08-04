import { describe, expect, it } from "vitest";

import {
  GROUPS,
  TAXONOMY_VERSION,
  groupOfLeaf,
  leavesForFields,
  parseFields,
  serialiseFields,
} from "@/lib/fields";

describe("the taxonomy", () => {
  it("is the same file the generation pass reads", () => {
    // If this ever came from a second copy, a story would be filed under one
    // field and shown under another.
    expect(TAXONOMY_VERSION).toMatch(/^fields-v/);
    expect(GROUPS.length).toBeGreaterThan(0);
  });

  it("puts every leaf in exactly one group", () => {
    const seen = new Map<string, string>();
    for (const group of GROUPS) {
      for (const leaf of group.leaves) {
        expect(seen.has(leaf.slug), `${leaf.slug} is in two groups`).toBe(false);
        seen.set(leaf.slug, group.slug);
      }
    }
  });

  it("gives every group leaves and a note", () => {
    // A group with nothing behind it is a promise the corpus cannot keep —
    // five of v1's thirteen categories were exactly that.
    for (const group of GROUPS) {
      expect(group.leaves.length).toBeGreaterThan(0);
      expect(group.note.length).toBeGreaterThan(10);
    }
  });
});

describe("groupOfLeaf", () => {
  it("resolves a leaf to its group", () => {
    expect(groupOfLeaf("mathematics")).toBe("physical");
    expect(groupOfLeaf("neuroscience")).toBe("mind");
  });

  it("returns null for a story with no established field", () => {
    // NULL and "chemistry" have to stay different things: a story filed by
    // guesswork appears under a field its reader did not ask for.
    expect(groupOfLeaf(null)).toBeNull();
    expect(groupOfLeaf(undefined)).toBeNull();
    expect(groupOfLeaf("phrenology")).toBeNull();
  });
});

describe("parseFields", () => {
  it("reads a comma-separated selection", () => {
    expect(parseFields("life,space")).toEqual(["life", "space"]);
  });

  it("treats nothing chosen as everything, not as nothing", () => {
    // A reader who unticks their last field must get the feed back, not an
    // empty page they have to work out how to escape.
    expect(parseFields(undefined)).toEqual([]);
    expect(leavesForFields(parseFields(undefined))).toBeNull();
  });

  it("drops slugs that name no group rather than filtering to nothing", () => {
    expect(parseFields("life,astrology,space")).toEqual(["life", "space"]);
    expect(parseFields("astrology")).toEqual([]);
  });

  it("ignores a repeated slug", () => {
    expect(parseFields("life,life")).toEqual(["life"]);
  });

  it("rejects a leaf where a group is expected", () => {
    // The URL carries groups. Accepting a leaf here would filter to something
    // the control cannot display as selected.
    expect(parseFields("mathematics")).toEqual([]);
  });
});

describe("serialiseFields", () => {
  it("writes the taxonomy's order, so one selection makes one URL", () => {
    expect(serialiseFields(["space", "life"])).toBe(
      serialiseFields(["life", "space"]),
    );
  });

  it("round-trips through parseFields", () => {
    const chosen = ["life", "physical", "space"];
    expect(parseFields(serialiseFields(chosen))).toEqual(chosen);
  });
});

describe("leavesForFields", () => {
  it("expands a group to all of its leaves", () => {
    const leaves = leavesForFields(["physical"]) ?? [];
    expect(leaves).toContain("mathematics");
    expect(leaves).toContain("chemistry");
    expect(leaves).not.toContain("neuroscience");
  });

  it("asks for no restriction when nothing is chosen", () => {
    // Not "every leaf": a story whose field was never established carries
    // NULL, and listing leaves would silently drop it from Everything.
    expect(leavesForFields([])).toBeNull();
  });
});
