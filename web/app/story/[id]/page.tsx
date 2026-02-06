import { notFound, redirect } from 'next/navigation';

import { getClusterDetail } from '@/lib/api/clusters';
import { StoryPage } from '@/components/story/StoryPage/StoryPage';

export default async function Story({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getClusterDetail(id);
  if (result.kind === 'redirect') {
    redirect(`/story/${result.toId}`);
  }
  if (result.kind === 'not_found') {
    notFound();
  }
  return <StoryPage cluster={result.cluster} />;
}
