import { notFound, redirect } from 'next/navigation';

import { getClusterUpdates } from '@/lib/api/updates';
import { UpdatesPage } from '@/components/story/UpdatesPage/UpdatesPage';

export default async function StoryUpdates({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getClusterUpdates(id);
  if (result.kind === 'redirect') {
    redirect(`/story/${result.toId}/updates`);
  }
  if (result.kind === 'not_found') {
    notFound();
  }
  return <UpdatesPage clusterId={id} updates={result.updates} />;
}
