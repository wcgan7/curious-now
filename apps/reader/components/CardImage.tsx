"use client";

import Image from "next/image";
import type { CSSProperties } from "react";
import { useState } from "react";

import { type Frame, frameFor, sameFrame } from "@/lib/imagery";
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
 * Served through Next's optimiser rather than hotlinked. The bytes on the other
 * end are a paper's full-resolution figure, up to 3.6 MB of it, for a frame
 * 390px wide; sixty cards of feed came to 12.9 MB and the tail of it never
 * arrived, because a browser will only hold six connections open to arxiv.org.
 *
 * The interesting behaviour is still failure: a card whose image does not load
 * must become the card it would have been without one, not a card with a hole
 * in it. A host missing from next.config.ts fails exactly that way.
 */
export function CardImage({ source }: { source: SourceLink | undefined }) {
  const [failed, setFailed] = useState(false);
  // The frame's shape, once the image has reported its own. Nothing stores the
  // dimensions — the extractor records a figure's label, caption and URL and
  // not its pixels — so the load event is the only place to learn them. A
  // figure starts contained at the default shape, which is why it never
  // flashes cropped.
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
      <Image
        alt=""
        aria-hidden="true"
        fill
        onError={() => setFailed(true)}
        onLoad={(event) => {
          // The optimiser preserves the aspect ratio, so the resized image
          // reports the same shape the original had.
          const image = event.currentTarget;
          const next = frameFor(kind, image.naturalWidth, image.naturalHeight);
          setFrame((current) => (sameFrame(current, next) ? current : next));
        }}
        // The feed is a phone layout centred in 44rem, so a card is never
        // wider than that and usually the width of the screen.
        sizes="(max-width: 44rem) 100vw, 44rem"
        src={src}
      />
    </div>
  );
}
