"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { CardImage } from "@/components/CardImage";
import { serialiseFields } from "@/lib/fields";
import { vettingSource } from "@/lib/provenance";
import type { FeedPage, FeedStory } from "@/lib/types";

/** How long ago the science appeared.
 *
 * Day-level, because that is all the sources give: 84% of ingested items land
 * exactly on the hour — arXiv stamps everything 04:00, eLife and medRxiv 00:00
 * — so an exact time would be a false claim.
 */
function ago(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const days = Math.round((Date.now() - Date.parse(iso)) / 86_400_000);
  if (!Number.isFinite(days)) {
    return "";
  }
  const plural = (count: number, unit: string) =>
    `${count} ${unit}${count === 1 ? "" : "s"} ago`;
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return plural(days, "day");
  if (days < 60) return plural(Math.round(days / 7), "week");
  return plural(Math.round(days / 30), "month");
}

/** A story is a row: picture edge to edge, text on one margin, hairline below.
 *
 * What is *not* here is most of what used to be. A badge saying "Preprint"
 * under a source called "arXiv machine learning"; a date identical on every
 * visible card; a depth count identical on every visible card. All three were
 * constant at the top of the feed by construction — ranking selects for those
 * properties, so the cards it puts first cannot differ in them — and a label
 * that reads the same on every row is texture, not information.
 */
function StoryRow({ story }: { story: FeedStory }) {
  const source = vettingSource(story.sources);
  const hasPicture = Boolean(source?.imageUrl || source?.figureImage);
  const isFigure = Boolean(source && !source.imageUrl && source.figureImage);

  return (
    <li className="story">
      <Link className="storyLink" href={`/story/${story.id}`}>
        {hasPicture ? (
          <span className={isFigure ? "storyPicture storyPicture--figure" : "storyPicture"}>
            <CardImage source={source} />
          </span>
        ) : null}
        <span className="storyBody">
          <span className="storyMeta">
            <span className="storySource">{source?.sourceName}</span>
            <time className="storyWhen" dateTime={story.publishedAt}>
              {ago(story.publishedAt)}
            </time>
          </span>
          <h2 className="storyTitle">{story.title}</h2>
        </span>
      </Link>
    </li>
  );
}

/**
 * The feed, and what it says when it runs out.
 *
 * Pages are fetched through the API route so the filter has to travel with the
 * cursor: without it, scrolling a filtered feed quietly returns to everything.
 */
export function FeedStream({
  fields,
  initialPage,
}: {
  fields: readonly string[];
  initialPage: FeedPage;
}) {
  const [stories, setStories] = useState<FeedStory[]>(initialPage.stories);
  const [cursor, setCursor] = useState<string | null>(initialPage.nextCursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);

  // A new selection is a new feed, not more of the old one.
  useEffect(() => {
    setStories(initialPage.stories);
    setCursor(initialPage.nextCursor);
    setFailed(false);
  }, [initialPage]);

  const loadMore = useCallback(async () => {
    if (!cursor || loading) {
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const query = new URLSearchParams({ cursor });
      if (fields.length > 0) {
        query.set("fields", serialiseFields(fields));
      }
      const response = await fetch(`/api/feed?${query}`);
      if (!response.ok) {
        throw new Error(String(response.status));
      }
      const page: FeedPage = await response.json();
      setStories((current) => [...current, ...page.stories]);
      setCursor(page.nextCursor);
    } catch {
      // Kept rather than swallowed: a feed that silently stops looks identical
      // to a feed that ended, and the reader would never think to retry.
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [cursor, fields, loading]);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !cursor) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadMore();
        }
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [cursor, loadMore]);

  if (stories.length === 0) {
    return (
      <p className="feedNotice">
        Nothing here yet. Try another field, or clear the filter.
      </p>
    );
  }

  return (
    <>
      <ul className="feed">
        {stories.map((story) => (
          <StoryRow key={story.id} story={story} />
        ))}
      </ul>

      <div aria-hidden="true" ref={sentinel} />

      {failed ? (
        <p className="feedNotice">
          Could not load more.{" "}
          <button className="searchCancel" onClick={() => void loadMore()} type="button">
            Try again
          </button>
        </p>
      ) : loading ? (
        <p className="feedNotice">Loading…</p>
      ) : !cursor ? (
        <p className="feedNotice">That is the end of the feed.</p>
      ) : null}
    </>
  );
}
