import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StoryReader } from "@/components/StoryReader";
import { getStory } from "@/lib/data";

export const dynamic = "force-dynamic";

interface StoryPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ view?: string | string[] }>;
}

export async function generateMetadata({
  params,
}: StoryPageProps): Promise<Metadata> {
  const { id } = await params;
  const story = await getStory(id);
  return story ? { title: story.title } : { title: "Story not found" };
}

/** No shell and no back link.
 *
 * The picture is the first thing on the page and full-bleed, so a container
 * with padding would inset it and a "← Back to the feed" row would push it
 * below the fold. The masthead is above every page and its wordmark goes home,
 * which is the same journey in a place that costs nothing.
 */
export default async function StoryPage({ params, searchParams }: StoryPageProps) {
  const { id } = await params;
  const { view } = await searchParams;
  const story = await getStory(id);
  if (!story) {
    notFound();
  }

  return (
    <StoryReader
      initialView={typeof view === "string" ? view : undefined}
      story={story}
    />
  );
}
