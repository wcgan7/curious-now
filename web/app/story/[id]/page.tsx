import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { getClusterDetail } from '@/lib/api/clusters';
import { getClusterUpdates } from '@/lib/api/updates';
import { StoryPage } from '@/components/story/StoryPage/StoryPage';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  try {
    const result = await getClusterDetail(id);
    if (result.kind === 'ok') {
      const title = result.cluster.canonical_title;
      const description = result.cluster.takeaway ?? result.cluster.summary_intuition ?? undefined;
      return {
        title: `${title} | Curious Now`,
        description,
        openGraph: {
          title,
          description,
          ...(result.cluster.featured_image_url ? { images: [result.cluster.featured_image_url] } : {}),
        },
      };
    }
  } catch {
    // Fall through to defaults
  }
  return { title: 'Story | Curious Now' };
}

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
