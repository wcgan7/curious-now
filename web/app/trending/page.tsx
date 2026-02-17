import { FeedPage } from '@/components/feed/FeedPage/FeedPage';

export const metadata = { title: 'In Focus | Curious Now', description: 'Trending science stories curated from multiple sources.' };

export default async function TrendingPage() {
  return <FeedPage tab="trending" />;
}

