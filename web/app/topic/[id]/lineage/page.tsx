import { notFound, redirect } from 'next/navigation';

import { getTopicLineage } from '@/lib/api/topics';
import { LineagePage } from '@/components/topic/LineagePage/LineagePage';
import { env } from '@/lib/config/env';

export default async function TopicLineage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!env.features.lineage) {
    notFound();
  }
  const result = await getTopicLineage(id);
  if (result.kind === 'redirect') {
    redirect(`/topic/${result.toId}/lineage`);
  }
  if (result.kind === 'not_found') {
    notFound();
  }
  return <LineagePage lineage={result.lineage} />;
}
