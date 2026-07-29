import type { Metadata } from "next";
import Link from "next/link";

import { SearchResults } from "@/components/SearchResults";
import { searchStories } from "@/lib/data";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Search · Curious Now" };

interface SearchPageProps {
  searchParams: Promise<{ q?: string | string[] }>;
}

export default async function SearchPage({ searchParams }: SearchPageProps) {
  const { q } = await searchParams;
  const query = (typeof q === "string" ? q : "").trim();
  const stories = query ? await searchStories(query) : [];

  return (
    <section className="feedSection" aria-labelledby="search-heading">
      <Link className="backLink" href="/">
        <span aria-hidden="true">←</span> Back to the feed
      </Link>

      <div className="sectionHeading">
        <div>
          <p className="sectionKicker">Search the shelf</p>
          <h2 id="search-heading">
            {query ? `Results for “${query}”` : "Find a story"}
          </h2>
        </div>
      </div>

      <form action="/search" className="searchForm" role="search">
        <label className="visuallyHidden" htmlFor="q">
          Search stories
        </label>
        <input
          autoComplete="off"
          defaultValue={query}
          id="q"
          name="q"
          placeholder="Search titles and sources…"
          type="search"
        />
        <button className="primaryButton" type="submit">
          Search
        </button>
      </form>

      <SearchResults query={query} stories={stories} />
    </section>
  );
}
