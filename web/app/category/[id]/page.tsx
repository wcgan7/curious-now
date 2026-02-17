import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { TopicPage } from '@/components/topic/TopicPage/TopicPage';
import { getTopicDetail } from '@/lib/api/topics';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  try {
    const result = await getTopicDetail(id);
    if (result.kind === 'ok') {
      return {
        title: `${result.detail.topic.name} | Curious Now`,
        description: result.detail.topic.description_short ?? `Science stories in ${result.detail.topic.name}.`,
      };
    }
  } catch {
    // Fall through to defaults
  }
  return { title: 'Category | Curious Now' };
}

export default async function CategoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getTopicDetail(id);
  if (result.kind === 'redirect') {
    redirect(`/category/${result.toId}`);
  }
  if (result.kind === 'not_found') {
    notFound();
  }
  return <TopicPage detail={result.detail} />;
}
