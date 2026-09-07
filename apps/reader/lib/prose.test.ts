import { describe, expect, it } from "vitest";

import { renderProse } from "@/lib/prose";

describe("renderProse", () => {
  it("turns generated headings, bullets, and quotes into semantic blocks", () => {
    const blocks = renderProse(
      [
        "An opening paragraph.",
        "",
        "## Core contribution",
        "",
        "- First result.",
        "",
        "- Second result.",
        "",
        "> a compact statement",
      ].join("\n"),
      { inferHeadings: true },
    );

    expect(blocks.map((block) => block.kind)).toEqual([
      "paragraph",
      "heading",
      "list",
      "quote",
    ]);
    expect(blocks[2]).toMatchObject({ kind: "list", ordered: false });
    expect(blocks[2]?.kind === "list" ? blocks[2].items : []).toHaveLength(2);
  });

  it("recognises restrained prose headings without promoting a sentence", () => {
    const blocks = renderProse(
      "Why this is nontrivial\n\nThis is a complete sentence.",
      { inferHeadings: true },
    );

    expect(blocks[0]).toMatchObject({ kind: "heading", level: 2 });
    expect(blocks[1]).toMatchObject({ kind: "paragraph" });
  });

  it("distinguishes numbered subheads from a numbered list", () => {
    const subhead = renderProse("1. Atomic polynomials", { inferHeadings: true });
    const list = renderProse("1. A longer item that ends as a sentence.\n2. Another item.", {
      inferHeadings: true,
    });

    expect(subhead[0]).toMatchObject({ kind: "heading", level: 3 });
    expect(list[0]).toMatchObject({ kind: "list", ordered: true });
  });

  it("renders emphasis, inline code, and multiline mathematics safely", () => {
    const blocks = renderProse(
      "Use **the estimator** and `T40.7`.\n\n\\[\nx^2 + y^2\n\\]",
    );
    const html = blocks
      .flatMap((block) =>
        block.kind === "list" ? block.items.map((item) => item.html) : [block.value.html],
      )
      .join(" ");

    expect(html).toContain("<strong>the estimator</strong>");
    expect(html).toContain('<code class="inlineCode">T40.7</code>');
    expect(html).toContain("katex-display");
  });

  it("never accepts model-authored HTML", () => {
    const blocks = renderProse("<script>alert(1)</script>");
    const html = blocks[0]?.kind === "paragraph" ? blocks[0].value.html : "";

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
