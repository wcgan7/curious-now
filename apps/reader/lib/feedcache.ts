import type { FeedStory } from "@/lib/types";

/**
 * The feed a reader had, kept for as long as it takes them to read one story.
 *
 * The feed is an infinite scroll: page one is server-rendered and every page
 * after it is fetched into client state. That state does not survive leaving
 * the page. /story/[id] and / are both force-dynamic, so Next does not keep
 * dynamic segments in its client router cache, and coming back re-runs the
 * server component and mounts a fresh FeedStream holding page one.
 *
 * The reader sees that as a scroll position that misses, and misses by more the
 * further they had gone: measured, a feed at 8,929px across 100 cards came back
 * to 5,340px across 40, because the browser restored a scroll position into a
 * document that had lost two thirds of its height. Restoring only the position
 * cannot fix it. The pages have to come back too.
 */
const PREFIX = "feed:";
/** Long enough to read a story, short enough that a feed opened tomorrow is
 *  today's. */
const FRESH_FOR_MS = 30 * 60 * 1000;

interface Snapshot {
  stories: FeedStory[];
  cursor: string | null;
  /** The story that was at the top of the screen, and where in the screen.
   *
   * Not a pixel offset into the document. A figure card reserves 205px until
   * its image reports a size and then settles between 150px and 195px, so
   * every picture still in flight above the reader changes the height of the
   * document underneath them. Restoring to 8,929px landed 660px out for
   * exactly that reason. Restoring "this story, 40px from the top" cannot: it
   * is measured from the thing the reader was looking at. */
  anchorId: string;
  anchorTop: number;
  savedAt: number;
}

function key(fields: readonly string[]): string {
  // Per selection, because a snapshot of everything is not a snapshot of
  // physics and restoring one into the other would be a lie about what the
  // reader was looking at.
  return PREFIX + [...fields].sort().join(",");
}

/**
 * Whether the last navigation was backwards.
 *
 * Restoring on every arrival would be wrong: tapping the wordmark means "take
 * me home" and should not land someone 9,000px down. Only a back or forward
 * step is a request to be put back where they were, and popstate is what both
 * the browser's own gesture and router.back() raise.
 *
 * Module state rather than sessionStorage because it must not survive a reload
 * — a reader who reloads is asking for the page, not for their history.
 */
let arrivedByHistory = false;

if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    arrivedByHistory = true;
  });
}

export function consumeHistoryArrival(): boolean {
  const value = arrivedByHistory;
  arrivedByHistory = false;
  return value;
}

export function saveFeed(
  fields: readonly string[],
  snapshot: Omit<Snapshot, "savedAt">,
): void {
  try {
    window.sessionStorage.setItem(
      key(fields),
      JSON.stringify({ ...snapshot, savedAt: Date.now() }),
    );
  } catch {
    // Private mode, a full quota, a browser that has disabled it. A feed that
    // starts from the top is a worse experience, not a broken one.
  }
}

export function readFeed(fields: readonly string[]): Snapshot | null {
  try {
    const raw = window.sessionStorage.getItem(key(fields));
    if (!raw) {
      return null;
    }
    const value = JSON.parse(raw) as Partial<Snapshot>;
    if (
      !Array.isArray(value.stories) ||
      value.stories.length === 0 ||
      typeof value.anchorId !== "string" ||
      typeof value.savedAt !== "number" ||
      Date.now() - value.savedAt > FRESH_FOR_MS
    ) {
      return null;
    }
    return {
      stories: value.stories,
      cursor: typeof value.cursor === "string" ? value.cursor : null,
      anchorId: value.anchorId,
      anchorTop: typeof value.anchorTop === "number" ? value.anchorTop : 0,
      savedAt: value.savedAt,
    };
  } catch {
    return null;
  }
}
