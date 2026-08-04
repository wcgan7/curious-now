"use client";

import Image from "next/image";
import type { CSSProperties } from "react";
import { useCallback, useState } from "react";

import { Lightbox } from "@/components/Lightbox";
import {
  STORY_MIN_FRAME_ASPECT,
  captionFor,
  type Frame,
  frameFor,
  sameFrame,
} from "@/lib/imagery";
import type { SourceLink } from "@/lib/types";

/**
 * The picture at the top of a story page.
 *
 * The same two kinds as the feed and the same framing rules, with three things
 * changed because the reader has arrived rather than passed by.
 *
 * It opens. A band of at most 279px cannot make a paper's Figure 1 legible —
 * five stacked panels at 996×1466 — and a band tall enough to try would be the
 * page. So the band stays a band and a tap gives the whole thing, full screen,
 * with the whole caption. Everything else here follows from that: the preview
 * is a doorway, so it can be a consistent shape rather than a faithful one.
 *
 * It is described, and the description is the paper's. On a card the picture is
 * a thumbnail identifying a story the title already names, so it carries no alt
 * text and is hidden from screen readers. Here it is the paper's own figure,
 * and the first sentence of its caption is the sentence the authors wrote to
 * say what it shows — better alt text than anything we could compose, and the
 * only place the caption fits without putting a third line of grey between the
 * picture and the headline.
 *
 * The whole caption, all 53 median words of it, is in the lightbox.
 */
export function StoryImage({
  source,
  title,
}: {
  source: SourceLink | undefined;
  title: string;
}) {
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  // Nothing stores the image's dimensions, so the load event is the only place
  // to learn them; until it fires the figure is contained at the default
  // shape, which is why it never flashes cropped.
  const [frame, setFrame] = useState<Frame | null>(null);

  const figure = source?.figureImage;
  const src = source?.imageUrl ?? figure?.url ?? null;
  const kind = source?.imageUrl ? "photo" : "figure";

  /** Measure on load, and also on mount if the load already happened.
   *
   * This image is not lazy — it is the first thing on the page, so waiting for
   * the viewport would mean waiting for nothing. That is what makes the second
   * half necessary: a cached image is already complete before React hydrates
   * and attaches onLoad, so the event never fires and the figure keeps the
   * default frame forever.
   */
  const settle = useCallback(
    (image: HTMLImageElement | null | undefined) => {
      if (!image?.complete || image.naturalWidth === 0) {
        return;
      }
      const next = frameFor(
        kind,
        image.naturalWidth,
        image.naturalHeight,
        STORY_MIN_FRAME_ASPECT,
      );
      setFrame((current) => (sameFrame(current, next) ? current : next));
    },
    [kind],
  );

  if (!src || failed) {
    return null;
  }

  const shape = frame ?? frameFor(kind, 0, 0, STORY_MIN_FRAME_ASPECT);
  const alt =
    kind === "figure"
      ? (captionFor(figure?.caption) ?? `${figure?.label ?? "Figure"} from ${title}`)
      : title;

  return (
    <figure className="storyFigure">
      <button
        aria-label={`Open ${kind === "figure" ? "the figure" : "the picture"}`}
        className={`storyFigureFrame storyFigureFrame--${shape.fit}`}
        onClick={() => setOpen(true)}
        style={{ "--frame-aspect": shape.aspect } as CSSProperties}
        type="button"
      >
        <Image
          alt={alt}
          fill
          onError={() => setFailed(true)}
          // The optimiser preserves the aspect ratio, so the resized image
          // reports the same shape the original had.
          onLoad={(event) => settle(event.currentTarget)}
          // Eager, and given priority: this is the first thing on the page.
          priority
          ref={settle}
          sizes="(max-width: 44rem) 100vw, 44rem"
          src={src}
        />
        {/* A cursor says zoom-in and a thumb has no cursor. */}
        <span aria-hidden="true" className="storyFigureOpen" />
      </button>
      {open ? (
        <Lightbox
          alt={alt}
          caption={kind === "figure" ? figure?.caption : null}
          captionHtml={kind === "figure" ? figure?.captionHtml : null}
          onClose={() => setOpen(false)}
          src={src}
        />
      ) : null}
    </figure>
  );
}
