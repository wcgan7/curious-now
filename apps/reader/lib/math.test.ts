import { describe, expect, it } from "vitest";

import { hasMath, renderMath } from "@/lib/math";

const INLINE = String.raw`the ratio \(a/b\) grows`;
const DISPLAY = String.raw`\[E = mc^2\]`;

describe("renderMath", () => {
  it("typesets an inline formula", () => {
    const html = renderMath(INLINE);

    expect(html).toContain("katex");
    expect(html).toContain("grows");
  });

  it("typesets every formula in a string, not just the first", () => {
    // The regression this exists for: a module-level /g/ regex carries
    // lastIndex between calls, so the second formula was silently skipped.
    const html = renderMath(
      String.raw`first \(x^2\) then \(y^2\) then \(z^2\)`,
    );

    expect(html.match(/katex/g)?.length ?? 0).toBeGreaterThanOrEqual(3);
  });

  it("does not depend on what was rendered before it", () => {
    // Same bug from the other direction: hasMath() used .test() on the shared
    // regex, corrupting the next renderMath() call. Three of six real cases
    // produced nothing.
    hasMath(INLINE);
    hasMath(INLINE);
    const after = renderMath(INLINE);

    expect(after).toEqual(renderMath(INLINE));
    expect(after).toContain("katex");
  });

  it("is a pure function of its input", () => {
    expect(renderMath(DISPLAY)).toEqual(renderMath(DISPLAY));
  });

  it("escapes prose so explanation text cannot inject markup", () => {
    // Explanation text is model output. It is not markup and is not trusted.
    const html = renderMath('a <script>alert("x")</script> b');

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("does not let a formula smuggle markup through KaTeX", () => {
    const html = renderMath(String.raw`\(\href{javascript:alert(1)}{x}\)`);

    expect(html).not.toContain("javascript:");
  });

  it("keeps unparseable maths visible rather than dropping it", () => {
    // Silence would leave a sentence referring to an equation that is not
    // there; showing the source is honest and repairable.
    const html = renderMath(String.raw`\(\frac{\unknownmacro}\)`);

    expect(html).toContain("mathRaw");
  });

  it("leaves prose with no maths untouched apart from escaping", () => {
    expect(renderMath("plain sentence")).toBe("plain sentence");
  });

  it("handles an empty string", () => {
    expect(renderMath("")).toBe("");
  });
});

describe("hasMath", () => {
  it("finds maths anywhere in the string, not only at the start", () => {
    expect(hasMath(`a long preamble before ${INLINE}`)).toBe(true);
  });

  it("returns the same answer when asked twice", () => {
    expect(hasMath(INLINE)).toBe(hasMath(INLINE));
  });

  it("is false for prose", () => {
    expect(hasMath("no formulas here at all")).toBe(false);
  });
});
