import Link from "next/link";

import type { FeedStory } from "@/lib/types";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function SearchResults({
  query,
  stories,
}: {
  query: string;
  stories: FeedStory[];
}) {
  if (!query) {
    return (
      <div className="emptyFeed">
        <h3>Search collected science.</h3>
        <p>
          Matches story titles and the original source titles behind each story.
        </p>
      </div>
    );
  }

  if (!stories.length) {
    return (
      <div className="emptyFeed">
        <p className="sectionKicker">No matches</p>
        <h3>Nothing on the shelf matches that yet.</h3>
        <p>Try a broader term, or browse the feed.</p>
      </div>
    );
  }

  return (
    <ol className="searchResults">
      {stories.map((story) => {
        const leadSource = story.sources[0];
        return (
          <li key={story.id}>
            <Link href={`/story/${story.id}`}>
              {story.titleHtml ? (
                <h3 dangerouslySetInnerHTML={{ __html: story.titleHtml }} />
              ) : (
                <h3>{story.title}</h3>
              )}
              <p>
                {leadSource?.sourceName ?? "Collected source"}
                {" · "}
                <time dateTime={story.publishedAt}>
                  {formatDate(story.publishedAt)}
                </time>
              </p>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
