"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { CardImage } from "@/components/CardImage";
import type { FeedPage, FeedStory, SourceLink } from "@/lib/types";

const roleLabels: Record<SourceLink["sourceRole"], string> = {
  primary_research: "Primary research",
  journalism: "Independent reporting",
  lab_announcement: "Lab announcement",
  institutional: "Institution",
  government: "Government",
  press_release: "Press release",
  discovery: "Discovery",
};

const reviewLabels: Partial<Record<SourceLink["contentType"], string>> = {
  preprint: "Preprint",
  peer_reviewed: "Peer reviewed",
  report: "Report",
  dataset: "Dataset",
};

const PAPER_TYPES: ReadonlyArray<SourceLink["contentType"]> = [
  "preprint",
  "peer_reviewed",
];

// "Peer reviewed" and "Preprint" are claims about how a piece of work was
// vetted, so they are withheld where nothing establishes them. That is narrower
// than it sounds: arXiv's feed carries preprints and nothing else, so its
// default describes every item on it. Only a feed known to carry several kinds
// — Nature sends research, news, comment and book reviews down one URL — leaves
// an unmatched item unclassified, and there the source's role is shown instead,
// which is true of every item and claims nothing unestablished.
function reviewBadge(source: SourceLink): string | undefined {
  if (source.contentTypeBasis === "feed_unmatched") {
    return undefined;
  }
  return reviewLabels[source.contentType];
}

function formatRelativeTime(value: string): string {
  const elapsedMs = Date.now() - new Date(value).getTime();
  const minutes = Math.round(elapsedMs / 60_000);
  if (minutes < 60) {
    return minutes <= 1 ? "just now" : `${minutes} minutes ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  }
  const days = Math.round(hours / 24);
  if (days < 8) {
    return days === 1 ? "yesterday" : `${days} days ago`;
  }
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

function StoryCard({ story, index }: { story: FeedStory; index: number }) {
  const leadSource = story.sources[0];
  const badge = leadSource
    ? (reviewBadge(leadSource) ?? roleLabels[leadSource.sourceRole])
    : "Evidence";
  const paperAttached =
    leadSource !== undefined &&
    !PAPER_TYPES.includes(leadSource.contentType) &&
    story.sources.some(
      (source) =>
        PAPER_TYPES.includes(source.contentType) &&
        source.contentTypeBasis !== "feed_unmatched",
    );

  return (
    <Link className="storyCard" href={`/story/${story.id}`}>
      <div className="cardRail" aria-hidden="true">
        {String(index + 1).padStart(2, "0")}
      </div>
      <div className="cardBody">
        <div className="cardMeta">
          <span className={`sourceRole sourceRole--${leadSource?.sourceRole}`}>
            {badge}
          </span>
          <time dateTime={story.publishedAt} suppressHydrationWarning>
            {formatRelativeTime(story.publishedAt)}
          </time>
        </div>

        <h3>{story.title}</h3>

        <div className="cardFooter">
          <p className="sourceByline">
            {leadSource?.sourceName ?? "Collected source"}
            {paperAttached ? " · Paper attached" : ""}
          </p>
          <span className="cardArrow" aria-hidden="true">
            →
          </span>
        </div>
      </div>
      <CardImage source={leadSource} />
    </Link>
  );
}

export function FeedStream({ initialPage }: { initialPage: FeedPage }) {
  const [stories, setStories] = useState(initialPage.stories);
  const [cursor, setCursor] = useState(initialPage.nextCursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !cursor || loading || failed) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) {
          return;
        }
        setLoading(true);
        setFailed(false);
        fetch(`/api/feed?cursor=${encodeURIComponent(cursor)}`)
          .then(async (response) => {
            if (!response.ok) {
              throw new Error("feed request failed");
            }
            return (await response.json()) as FeedPage;
          })
          .then((page) => {
            setStories((current) => {
              const seen = new Set(current.map((story) => story.id));
              return [
                ...current,
                ...page.stories.filter((story) => !seen.has(story.id)),
              ];
            });
            setCursor(page.nextCursor);
          })
          .catch(() => setFailed(true))
          .finally(() => setLoading(false));
      },
      { rootMargin: "500px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [cursor, failed, loading]);

  if (!stories.length) {
    return (
      <div className="emptyFeed">
        <p className="sectionKicker">The shelf is empty</p>
        <h3>No stories have been collected yet.</h3>
        <p>Run the scheduled ingestion command, then refresh this page.</p>
      </div>
    );
  }

  return (
    <>
      <div className="feedList">
        {stories.map((story, index) => (
          <StoryCard index={index} key={story.id} story={story} />
        ))}
      </div>
      <div className="feedSentinel" ref={sentinel}>
        {loading ? <span>Collecting the next shelf…</span> : null}
        {failed ? (
          <button
            onClick={() => {
              setFailed(false);
              setLoading(false);
            }}
            type="button"
          >
            Try loading more
          </button>
        ) : null}
        {!cursor && stories.length ? <span>You reached the beginning.</span> : null}
      </div>
    </>
  );
}
