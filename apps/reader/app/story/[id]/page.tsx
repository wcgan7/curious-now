import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { StoryReader } from "@/components/StoryReader";
import { getStory } from "@/lib/data";

export const dynamic = "force-dynamic";

interface StoryPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({
  params,
}: StoryPageProps): Promise<Metadata> {
  const { id } = await params;
  const story = await getStory(id);
  return story ? { title: story.title } : { title: "Story not found" };
}

export default async function StoryPage({ params }: StoryPageProps) {
  const { id } = await params;
  const story = await getStory(id);
  if (!story) {
    notFound();
  }

  return (
    <article className="storyShell">
      <Link className="backLink" href="/">
        <span aria-hidden="true">←</span> Back to the feed
      </Link>
      <StoryReader story={story} />
    </article>
  );
}
