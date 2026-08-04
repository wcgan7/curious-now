"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { GROUPS, parseFields, serialiseFields } from "@/lib/fields";

/** The name, and one way in.
 *
 * The bar carried three controls in three visual languages — a text summary
 * with a chevron, an outlined magnifier, three dots — and two of them were
 * disclosure affordances sitting next to each other. Five rearrangements of
 * those three did not fix it, because the problem was that a 52px strip is not
 * enough room for three unrelated things and they end up competing for it.
 *
 * So there is one affordance, and what it opens has room. Search, the fields
 * with their counts, and appearance are one panel: everything that decides what
 * this reader sees, in one place, at a size where each can be itself.
 *
 * What this costs is the selection no longer being visible while scrolling,
 * which was the argument for putting a summary in the bar. The dot on the glyph
 * is the smallest honest replacement: it says a filter is on without spending a
 * row to say which.
 */
export function Masthead() {
  return (
    // useSearchParams needs a boundary, and without one every page rendering
    // this header opts out of static rendering entirely.
    <Suspense fallback={<Bar />}>
      <MastheadInner />
    </Suspense>
  );
}

function Bar({ children }: { children?: React.ReactNode }) {
  return (
    <header className="masthead">
      <Link className="wordmark" href="/">
        curious<span>.now</span>
      </Link>
      {children}
    </header>
  );
}

function MastheadInner() {
  const params = useSearchParams();
  const chosen = parseFields(params.get("fields") ?? undefined);
  const query = params.get("q") ?? "";
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    // The page behind must not scroll under an open drawer.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open]);

  // Deliberately not focused on open. Focus would raise the keyboard, and most
  // openings are to change a field rather than to type.
  useEffect(() => {
    if (open) {
      panel.current?.focus();
    }
  }, [open]);

  const filtered = chosen.length > 0 || Boolean(query);

  return (
    <>
      <Bar>
        <button
          aria-expanded={open}
          aria-label={filtered ? "Menu — a filter is on" : "Menu"}
          className="menuButton"
          onClick={() => setOpen(true)}
          type="button"
        >
          <span aria-hidden="true" className="glyphMenu" data-filtered={filtered} />
        </button>
      </Bar>

      {open ? (
        <Drawer
          chosen={chosen}
          onClose={() => setOpen(false)}
          panelRef={panel}
          query={query}
        />
      ) : null}
    </>
  );
}

function Drawer({
  chosen,
  onClose,
  panelRef,
  query,
}: {
  chosen: readonly string[];
  onClose: () => void;
  panelRef: React.RefObject<HTMLDivElement | null>;
  query: string;
}) {
  /** Where tapping a field leads: this selection with that one flipped. */
  const toggled = (slug: string) => {
    const next = chosen.includes(slug)
      ? chosen.filter((entry) => entry !== slug)
      : [...chosen, slug];
    const value = serialiseFields(next);
    return value ? `/?fields=${value}` : "/";
  };

  return (
    <>
      <button
        aria-label="Close"
        className="scrim"
        onClick={onClose}
        type="button"
      />
      <div
        aria-label="Menu"
        className="drawer"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="drawerHead">
          <span className="drawerTitle">Menu</span>
          <button
            aria-label="Close"
            className="menuButton"
            onClick={onClose}
            type="button"
          >
            <span aria-hidden="true" className="glyphClose" />
          </button>
        </div>

        <form action="/search" className="drawerSearch" role="search">
          <span aria-hidden="true" className="glyphSearch" />
          <input
            aria-label="Search stories"
            defaultValue={query}
            name="q"
            placeholder="Search stories"
            type="search"
          />
        </form>

        <p className="panelLabel">Your feed</p>
        <ul className="fieldList">
          <li>
            <Link
              className={chosen.length === 0 ? "fieldRow fieldRow--on" : "fieldRow"}
              href="/"
              scroll={false}
            >
              <span aria-hidden="true" className="check" />
              <span className="fieldRowName">Everything</span>
            </Link>
          </li>
          {GROUPS.map((group) => {
            const on = chosen.includes(group.slug);
            return (
              <li key={group.slug}>
                <Link
                  aria-pressed={on}
                  className={on ? "fieldRow fieldRow--on" : "fieldRow"}
                  href={toggled(group.slug)}
                  scroll={false}
                >
                  <span aria-hidden="true" className="check" />
                  <span className="fieldRowBody">
                    <span className="fieldRowName">{group.label}</span>
                    {/* The leaves are the description. A sentence saying
                        "physics, chemistry, materials, and the maths behind
                        them" beside a list saying the same in fewer words was
                        the same fact twice — and the list is the better half,
                        because it is what the filter actually contains. */}
                    <span className="fieldRowLeaves">
                      {group.leaves.map((leaf) => leaf.label).join(" · ")}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>

        <p className="panelLabel panelLabel--split">Appearance</p>
        <ThemeToggle labelled />
      </div>
    </>
  );
}
