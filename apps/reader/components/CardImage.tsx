"use client";

import type { CSSProperties } from "react";
import { useState } from "react";

import { type Frame, frameFor } from "@/lib/imagery";
import type { SourceLink } from "@/lib/types";

/**
 * The picture on a card, which is one of two quite different things.
 *
 * Where a publisher syndicated a photograph, that. Where none exists — and no
 * preprint server or journal syndicates one, so this is the common case — the
 * paper's own first figure stands in. They are framed differently, because a
 * photograph's edges are background and a figure's edges are its axis labels.
 * See lib/imagery.
 *
 * Either way it is hotlinked from someone else's CDN, so it can 404, move or be
 * blocked without notice, and the only interesting behaviour here is failure: a
 * card whose image does not load must become the card it would have been
 * without one, not a card with a hole in it.
 */
export function CardImage({ source }: { source: SourceLink | undefined }) {
  const [failed, setFailed] = useState(false);
  // The frame's shape, once the image has reported its own. Nothing stores the
  // dimensions — the extractor records a figure's label, caption and URL and
  // not its pixels — so the load event is the only place to learn them. A
  // backfill at extraction time would let the server emit this and remove the
  // settle; until then a figure starts contained at the default shape, which
  // is why it never flashes cropped.
  const [frame, setFrame] = useState<Frame | null>(null);

  const figure = source?.figureImage;
  const src = source?.imageUrl ?? figure?.url ?? null;
  if (!src || failed) {
    return null;
  }

  const kind = source?.imageUrl ? "photo" : "figure";
  const shape = frame ?? frameFor(kind, 0, 0);

  return (
    <div
      className={`cardImage cardImage--${shape.fit}`}
      style={{ "--frame-aspect": shape.aspect } as CSSProperties}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- hotlinked to the
          publisher's CDN, never copied or re-served, so Next's optimiser has
          nothing to optimise and would only proxy someone else's bytes. */}
      <img
        alt=""
        aria-hidden="true"
        decoding="async"
        loading="lazy"
        onError={() => setFailed(true)}
        onLoad={(event) => {
          const image = event.currentTarget;
          setFrame(frameFor(kind, image.naturalWidth, image.naturalHeight));
        }}
        src={src}
      />
    </div>
  );
}
