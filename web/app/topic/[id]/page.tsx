import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { getTopicDetail } from '@/lib/api/topics';
import { TopicPage } from '@/components/topic/TopicPage/TopicPage';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  try {
    const result = await getTopicDetail(id);
    if (result.kind === 'ok') {
      return {
        title: `${result.detail.topic.name} | Curious Now`,
        description: result.detail.topic.description_short ?? `Science stories about ${result.detail.topic.name}.`,
      };
    }
  } catch {
    // Fall through to defaults
  }
  return { title: 'Topic | Curious Now' };
}

export default async function Topic({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getTopicDetail(id);
  if (result.kind === 'redirect') {
    redirect(`/topic/${result.toId}`);
  }
  if (result.kind === 'not_found') {
    notFound();
  }
  return <TopicPage detail={result.detail} />;
}
