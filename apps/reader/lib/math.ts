import katex from "katex";

/**
 * Typeset the mathematics in a passage, and escape everything else.
 *
 * The reader spec requires that a layer carrying an equation "typeset one
 * properly rather than printing raw markup", and until now Technical printed
 * `\mathbf{b}\in\mathbb{R}^{T}` at readers verbatim.
 *
 * This runs on the server so KaTeX never reaches the browser bundle, and the
 * result is HTML — which means the prose around the formulas has to be escaped
 * here rather than trusted. Explanation text is model output; it is not markup
 * and must never be treated as markup.
 *
 * Boundaries come from the source. The extractors delimit every formula they
 * recover, because LaTeXML and JATS both know exactly where one starts and
 * ends, and guessing at that downstream is how prose gets mangled: `p\in(1,2]`
 * after a comma is mathematics, and the comma is not.
 */

// \( … \) and \[ … \], the delimiters our extractors emit, plus the dollar
// forms a model sometimes reaches for on its own.
//
// Built fresh per call, deliberately. A shared /g/ regex carries `lastIndex`
// between calls, so one `hasMath` check silently made the next `renderMath`
// skip the start of its text — every formula in the passage lost, with no
// error anywhere.
const MATH_SOURCE =
  String.raw`\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$|(?<![$\\])\$(?!\$)(.+?)(?<![$\\])\$(?!\$)`;

function mathPattern(): RegExp {
  return new RegExp(MATH_SOURCE, "gs");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function typeset(tex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(tex.trim(), {
      displayMode,
      output: "html",
      strict: false,
      // Never let source TeX reach into the page: no \href, no \url, no
      // \includegraphics. A paper's macros are not a licence to emit links.
      trust: false,
      throwOnError: true,
    });
  } catch {
    // A formula KaTeX cannot parse is shown as the TeX it came from, marked as
    // mathematics. Failing loudly here would blank a section over one macro.
    return `<code class="mathRaw">${escapeHtml(tex.trim())}</code>`;
  }
}

export function renderMath(text: string): string {
  let out = "";
  let last = 0;

  for (const match of text.matchAll(mathPattern())) {
    out += escapeHtml(text.slice(last, match.index));
    const [inlineParen, display, displayDollar, inlineDollar] = [
      match[1],
      match[2],
      match[3],
      match[4],
    ];
    const tex = inlineParen ?? display ?? displayDollar ?? inlineDollar ?? "";
    out += typeset(tex, display !== undefined || displayDollar !== undefined);
    last = (match.index ?? 0) + match[0].length;
  }

  return out + escapeHtml(text.slice(last));
}

/** Whether a passage contains anything worth typesetting. */
export function hasMath(text: string): boolean {
  return mathPattern().test(text);
}
