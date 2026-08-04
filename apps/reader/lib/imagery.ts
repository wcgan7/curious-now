/** How to frame a card image.
 *
 * Two kinds arrive and they want opposite things.
 *
 * A **photograph** is composed. Its edges are background, so filling the frame
 * and cropping them costs nothing, and their aspect ratios cluster tightly
 * enough (0.91 to 2.73 across the corpus, median 1.78) that one fixed frame
 * suits nearly all of them. Cover, and no blank space anywhere.
 *
 * A **figure** is drawn to be read. Its edges are the axis labels, the legend
 * and the panel titles, so cropping them is not losing background — it is
 * cutting words in half, which is what a fixed frame was doing. And figures do
 * not cluster: they run from 0.54 to 4.65, so no single frame fits them.
 *
 * So a figure gets a frame shaped to itself and is never cropped. Where its
 * shape is one the layout can carry, the frame matches exactly and there is
 * neither crop nor empty space. Where it is extreme, the frame stops at the
 * limit and the remainder shows as ground — which is white, the same white the
 * figure is drawn on, so it reads as the figure's own margin rather than as a
 * gap.
 */

export type Fit = "cover" | "contain";

export interface Frame {
  /** width ÷ height, for CSS aspect-ratio. */
  aspect: number;
  fit: Fit;
}

/** One frame for every photograph. Slightly wider than their median, so most
 *  crop a little at top and bottom rather than at the sides. */
export const PHOTO_ASPECT = 1.9;

/**
 * How far a figure's frame may bend.
 *
 * The floor is what stops one image owning the screen, and it has come down
 * twice: 1.1 was 355px at a 390px width — 42% of a phone for one picture —
 * then 1.5 was 260px, and 2 is 195px.
 *
 * It is bought with white. A figure taller than the floor is not cropped to
 * fit, it is centred in a shorter frame, so the tighter the floor the more of
 * the frame is ground rather than picture. At 2 the median figure (1.79) shows
 * across 90% of the width and the tallest across 27%. That is affordable only
 * because the ground is the same white the figures are drawn on, so what is
 * left over reads as margin; against a tint this would look like a mistake.
 */
export const MIN_FRAME_ASPECT = 2.0;
export const MAX_FRAME_ASPECT = 2.6;

/**
 * The floor on a story page, where the picture is not competing with anything.
 *
 * The feed's floor is about scrolling: a reader is passing thirty cards and a
 * tall one blocks the road. On a story page the picture opens, so the band is
 * a doorway rather than the artifact and the question changes. It is no longer
 * "how much of this figure can a reader read here" — the answer to that is one
 * tap away — but "how tall a band can the top of a page carry".
 *
 * 1.4 is 279px at 390 wide, and every story page then opens on a band between
 * 150px and 279px whatever its picture. A 0.9 floor was tried first, when the
 * band still had to be the whole answer; it put a portrait figure at 433px and
 * pushed the headline off the screen to show panels that were still too small
 * to read.
 */
export const STORY_MIN_FRAME_ASPECT = 1.4;

/** The frame this image should sit in. */
export function frameFor(
  kind: "photo" | "figure",
  width: number,
  height: number,
  floor: number = MIN_FRAME_ASPECT,
): Frame {
  if (kind === "photo") {
    return { aspect: PHOTO_ASPECT, fit: "cover" };
  }
  if (!measurable(width, height)) {
    // Before the image reports its size there is nothing to shape the frame
    // to. Contain regardless: a figure briefly letterboxed is recoverable, a
    // figure briefly cropped has already cut a label by the time it settles.
    return { aspect: PHOTO_ASPECT, fit: "contain" };
  }
  const natural = width / height;
  return {
    aspect: Math.min(Math.max(natural, floor), MAX_FRAME_ASPECT),
    fit: "contain",
  };
}

/** Whether two frames are the same frame.
 *
 * frameFor builds a fresh object every call, so feeding its result straight to
 * setState makes every load a state change even when nothing changed — and with
 * next/image that is a render loop, because the re-render re-runs the callback
 * that produced it. React bails out of an update that returns the value it
 * already had, which is what this is for.
 */
export function sameFrame(a: Frame | null, b: Frame): boolean {
  return a !== null && a.aspect === b.aspect && a.fit === b.fit;
}

function measurable(width: number, height: number): boolean {
  return (
    Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0
  );
}

/**
 * A figure's caption, cut to the part that works as plain text.
 *
 * Scientific captions are written to one convention: a title sentence, then
 * everything needed to reproduce the panel. Across the 291 first-figures in
 * this corpus the whole caption runs a median of 53 words and as far as 304,
 * while its first sentence runs a median of 9. So the first sentence is the
 * caption a reader wants and the rest is apparatus — "note the differing
 * y-scales", "n = 12 per group", the statistical test.
 *
 * Where the first sentence is itself long the figure gets none, and the same
 * where it carries mathematics. 134 of the 291 captions do, and "Level scheme
 * of \(Q_{x}\)-transition in H 2 Pc" is not a description — it is markup read
 * aloud. The lightbox shows the whole caption with the maths typeset; this is
 * the version that has to survive being spoken.
 */
const CAPTION_WORD_LIMIT = 25;
const MATHEMATICS = /\\\(|\\\[|\$|\\[a-zA-Z]+\{/;

// Full stops that do not end a sentence. Decimals and version numbers are
// handled by the digit test; these are the words.
const ABBREVIATIONS =
  /\b(?:fig|figs|eq|eqs|ref|refs|al|e\.g|i\.e|cf|vs|approx|ca|no|nos|suppl|sec|vol|ed|eds|pp|st|dev)\.$/i;

export function captionFor(caption: string | null | undefined): string | null {
  // Stripping the caption's italics leaves a space before the punctuation that
  // followed them — "Overview of Baikal , on a real query" — which reads as a
  // typo in our prose rather than an artefact of theirs.
  const text = (caption ?? "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
  if (!text) {
    return null;
  }
  const first = firstSentence(text);
  if (MATHEMATICS.test(first) || first.split(" ").length > CAPTION_WORD_LIMIT) {
    return null;
  }
  return first;
}

function firstSentence(text: string): string {
  // A break is a stop, then space, then something that starts a sentence: a
  // capital, or — because this is a figure caption — a panel marker. The title
  // sentence usually runs straight into "a) Schematic of…", which is the
  // apparatus beginning in lower case.
  const breaks = /[.!?](?=\s+(?:[A-Z(“"'\\]|\(?[a-z]\)))/g;
  let match: RegExpExecArray | null;
  while ((match = breaks.exec(text)) !== null) {
    const head = text.slice(0, match.index + 1);
    // Not a break after "Fig." or "et al.", nor after a digit — "0.5" and
    // "Fig. 1. Overview" both put a stop where no sentence ends.
    if (ABBREVIATIONS.test(head) || /\d\.$/.test(head)) {
      continue;
    }
    return head;
  }
  return text;
}

/**
 * What fraction of the frame is ground rather than image.
 *
 * Exported because the promise the frame makes — that a figure is never cut,
 * and that what it costs instead is bounded — is only worth making if it can
 * be checked.
 */
export function emptyFraction(naturalAspect: number, frame: Frame): number {
  if (!(naturalAspect > 0) || !(frame.aspect > 0) || frame.fit === "cover") {
    return 0;
  }
  const ratio =
    naturalAspect > frame.aspect
      ? frame.aspect / naturalAspect
      : naturalAspect / frame.aspect;
  return 1 - ratio;
}
