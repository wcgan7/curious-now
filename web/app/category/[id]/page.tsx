import { notFound, redirect } from 'next/navigation';

import { TopicPage } from '@/components/topic/TopicPage/TopicPage';
import { getTopicDetail } from '@/lib/api/topics';

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
