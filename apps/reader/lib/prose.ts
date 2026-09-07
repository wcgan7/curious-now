import { renderMath } from "@/lib/math";
import type { ProseBlock, ProseFragment } from "@/lib/types";

interface ProseOptions {
  inferHeadings?: boolean;
}

const BULLET = /^[-*•]\s+(.+)$/s;
const NUMBERED = /^(\d+)[.)]\s+(.+)$/s;
const MARKDOWN_HEADING = /^(#{2,4})\s+(.+)$/s;

/** Add the small amount of inline structure the generation prompts produce.
 *
 * `renderMath` has already escaped every byte of model-written prose, so these
 * replacements can only wrap safe output. Formula HTML remains server-rendered
 * KaTeX and is never interpreted as model-authored markup.
 */
function inlineMarkup(html: string): string {
  return html
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`\n]+?)`/g, '<code class="inlineCode">$1</code>');
}

function fragment(text: string): ProseFragment {
  return { text, html: inlineMarkup(renderMath(text)) };
}

function looksLikeHeading(value: string): boolean {
  const words = value.split(/\s+/).filter(Boolean);
  return (
    value.length <= 72 &&
    words.length <= 9 &&
    /^[A-Z0-9]/.test(value) &&
    !/[.!?,;:]$/.test(value) &&
    !/[=<>]/.test(value) &&
    !/^\\[([]/.test(value)
  );
}

type Token =
  | { kind: "paragraph"; value: ProseFragment }
  | { kind: "heading"; level: 2 | 3; value: ProseFragment }
  | { kind: "quote"; value: ProseFragment }
  | { kind: "list-item"; ordered: boolean; value: ProseFragment };

function tokensFor(chunk: string, options: ProseOptions): Token[] {
  const lines = chunk
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return [];

  const heading = lines.length === 1 ? lines[0].match(MARKDOWN_HEADING) : null;
  if (heading) {
    return [
      {
        kind: "heading",
        level: heading[1].length >= 3 ? 3 : 2,
        value: fragment(heading[2]),
      },
    ];
  }

  if (lines.every((line) => line.startsWith(">"))) {
    return [
      {
        kind: "quote",
        value: fragment(lines.map((line) => line.replace(/^>\s?/, "")).join("\n")),
      },
    ];
  }

  const bullets = lines.map((line) => line.match(BULLET));
  if (bullets.every(Boolean)) {
    return bullets.map((match) => ({
      kind: "list-item",
      ordered: false,
      value: fragment(match?.[1] ?? ""),
    }));
  }

  const numbered = lines.map((line) => line.match(NUMBERED));
  if (numbered.every(Boolean)) {
    const only = numbered[0];
    if (
      lines.length === 1 &&
      only &&
      looksLikeHeading(only[2])
    ) {
      return [
        {
          kind: "heading",
          level: 3,
          value: fragment(`${only[1]}. ${only[2]}`),
        },
      ];
    }
    return numbered.map((match) => ({
      kind: "list-item",
      ordered: true,
      value: fragment(match?.[2] ?? ""),
    }));
  }

  const value = lines.join("\n");
  if (options.inferHeadings && lines.length === 1 && looksLikeHeading(value)) {
    return [{ kind: "heading", level: 2, value: fragment(value) }];
  }
  return [{ kind: "paragraph", value: fragment(value) }];
}

/** Turn the restrained structure already present in generated prose into a
 * serialisable presentation model. This is intentionally not a Markdown
 * renderer: links and arbitrary HTML are never accepted from model output.
 */
export function renderProse(text: string, options: ProseOptions = {}): ProseBlock[] {
  const tokens = text
    .trim()
    .split(/\n\s*\n+/)
    .flatMap((chunk) => tokensFor(chunk, options));
  const blocks: ProseBlock[] = [];

  for (const token of tokens) {
    if (token.kind !== "list-item") {
      blocks.push(token);
      continue;
    }
    const previous = blocks.at(-1);
    if (previous?.kind === "list" && previous.ordered === token.ordered) {
      previous.items.push(token.value);
    } else {
      blocks.push({ kind: "list", ordered: token.ordered, items: [token.value] });
    }
  }
  return blocks;
}
