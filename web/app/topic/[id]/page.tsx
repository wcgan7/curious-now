import { notFound, redirect } from 'next/navigation';

import { getTopicDetail } from '@/lib/api/topics';
import { TopicPage } from '@/components/topic/TopicPage/TopicPage';

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
