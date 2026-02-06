import { FeedPage } from '@/components/feed/FeedPage/FeedPage';

export default async function ForYouPage() {
  return <FeedPage tab="for_you" requireAuth />;
}

