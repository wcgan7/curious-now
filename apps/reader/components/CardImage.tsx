"use client";

import { useState } from "react";

import type { SourceLink } from "@/lib/types";

/**
 * The image a publisher syndicated with its own story.
 *
 * Hotlinked from their CDN, which means it can 404, move, or be blocked
 * without notice — so the only interesting behaviour here is failure. A card
 * whose image does not load must become the card it would have been without
 * one, not a card with a hole in it. That is the common case rather than the
 * exception: no preprint server or journal syndicates an image at all, so
 * roughly half the feed has none and must look deliberate anyway.
 *
 * Where a source syndicated nothing, a paper's own first figure stands in. It
 * is labelled, because a diagram from the work is not a photograph of it and a
 * reader should be able to tell which they are looking at.
 */
export function CardImage({ source }: { source: SourceLink | undefined }) {
  const [failed, setFailed] = useState(false);

  const figure = source?.figureImage;
  const src = source?.imageUrl ?? figure?.url ?? null;
  if (!src || failed) {
    return null;
  }

  return (
    <div className="cardImage">
      {/* eslint-disable-next-line @next/next/no-img-element -- hotlinked to the
          publisher's CDN, never copied or re-served, so Next's optimiser has
          nothing to optimise and would only proxy someone else's bytes. */}
      <img
        alt=""
        aria-hidden="true"
        decoding="async"
        loading="lazy"
        onError={() => setFailed(true)}
        src={src}
      />
      {!source?.imageUrl && figure ? (
        <span className="cardImageLabel">{figure.label ?? "Figure"}</span>
      ) : null}
    </div>
  );
}
