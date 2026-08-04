"use client";

import { useEffect, useRef } from "react";

/**
 * The picture, full size, with everything the page could not afford.
 *
 * The band at the top of a story page is a doorway: 279px at most, and a
 * paper's Figure 1 is routinely five stacked panels at 996×1466 that no band
 * can make legible. Rather than choose between a band that fits the page and a
 * figure a reader can read, the band stays a band and this is where the figure
 * is actually read — contained, as large as the screen allows, with the whole
 * caption rather than its first sentence.
 *
 * That is also what makes cropping a photograph defensible. A crop is only a
 * loss if it is the last word.
 */
export function Lightbox({
  alt,
  caption,
  captionHtml,
  onClose,
  src,
}: {
  alt: string;
  caption?: string | null;
  captionHtml?: string | null;
  onClose: () => void;
  src: string;
}) {
  const close = useRef<HTMLButtonElement>(null);
  const overlay = useRef<HTMLDivElement>(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      // Only the close button is focusable, so Tab has nowhere else to go and
      // letting it leave would put focus on a page the reader cannot see.
      if (event.key === "Tab") {
        event.preventDefault();
        close.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div
      aria-label={alt}
      aria-modal="true"
      className="lightbox"
      onClick={(event) => {
        if (event.target === overlay.current) {
          onClose();
        }
      }}
      ref={overlay}
      role="dialog"
    >
      <button
        aria-label="Close"
        className="lightboxClose"
        onClick={onClose}
        ref={close}
        type="button"
      >
        Close
      </button>
      {/* eslint-disable-next-line @next/next/no-img-element -- hotlinked to the
          publisher's CDN, never copied or re-served. */}
      <img alt={alt} className="lightboxImg" src={src} />
      {/* The html is produced by lib/math on the server: prose escaped,
          formulas typeset by KaTeX with trust disabled. Where none was
          produced the caption is rendered as text, never as markup. */}
      {captionHtml ? (
        <p
          className="lightboxCaption"
          dangerouslySetInnerHTML={{ __html: captionHtml }}
        />
      ) : caption ? (
        <p className="lightboxCaption">{caption}</p>
      ) : null}
    </div>
  );
}
