import { notFound, redirect } from 'next/navigation';

import { getClusterDetail } from '@/lib/api/clusters';
import { getClusterUpdates } from '@/lib/api/updates';
import { StoryPage } from '@/components/story/StoryPage/StoryPage';

export default async function Story({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [clusterResult, updatesResult] = await Promise.all([
    getClusterDetail(id),
    getClusterUpdates(id).catch(() => null),
  ]);

  if (clusterResult.kind === 'redirect') {
    redirect(`/story/${clusterResult.toId}`);
  }
  if (clusterResult.kind === 'not_found') {
    notFound();
  }

  const hasUpdates = updatesResult?.kind === 'ok' && updatesResult.updates.updates.length > 0;

  return <StoryPage cluster={clusterResult.cluster} hasUpdates={hasUpdates} />;
}
