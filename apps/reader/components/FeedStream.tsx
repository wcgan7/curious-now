"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

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

const contentLabels: Record<SourceLink["contentType"], string> = {
  news: "News",
  lab_announcement: "Lab post",
  press_release: "Press release",
  preprint: "Preprint · not peer reviewed",
  peer_reviewed: "Peer reviewed",
  report: "Report",
  blog: "Blog",
  dataset: "Dataset",
  other: "Source",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

function SourceByline({ sources }: { sources: SourceLink[] }) {
  const names = [...new Set(sources.map((source) => source.sourceName))];
  const remaining = Math.max(0, names.length - 2);
  return (
    <p className="sourceByline">
      {names.slice(0, 2).join(" · ")}
      {remaining > 0 ? ` · +${remaining} more` : ""}
    </p>
  );
}

function StoryCard({ story, index }: { story: FeedStory; index: number }) {
  const leadSource = story.sources[0];
  return (
    <article className="storyCard">
      <div className="cardRail" aria-hidden="true">
        {String(index + 1).padStart(2, "0")}
      </div>
      <div className="cardBody">
        <div className="cardMeta">
          <span className={`sourceRole sourceRole--${leadSource?.sourceRole}`}>
            {leadSource ? roleLabels[leadSource.sourceRole] : "Evidence"}
          </span>
          <time dateTime={story.publishedAt}>
            {formatDate(story.publishedAt)}
          </time>
        </div>

        <h3>
          <Link href={`/story/${story.id}`}>{story.title}</Link>
        </h3>

        {story.glance ? (
          <p className="glance">{story.glance}</p>
        ) : (
          <p className="evidenceOnly">
            Collected from the source. A grounded explanation has not been
            generated yet.
          </p>
        )}

        <div className="cardFooter">
          <div>
            <SourceByline sources={story.sources} />
            {leadSource ? (
              <p className="contentLabel">
                {contentLabels[leadSource.contentType]}
              </p>
            ) : null}
          </div>
          <div className="depthPills" aria-label="Available reading depths">
            {story.availableDepths.length ? (
              story.availableDepths.map((depth) => (
                <span key={depth}>{depth}</span>
              ))
            ) : (
              <span className="mutedPill">sources</span>
            )}
            <Link
              aria-label={`Read ${story.title}`}
              className="cardArrow"
              href={`/story/${story.id}`}
            >
              ↗
            </Link>
          </div>
        </div>
      </div>
    </article>
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
