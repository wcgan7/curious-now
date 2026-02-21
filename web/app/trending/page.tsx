import { FeedPage } from '@/components/feed/FeedPage/FeedPage';

export const metadata = { title: 'In Focus | Curious Now', description: 'High-impact science stories with recency-aware ranking.' };

export default async function TrendingPage() {
  return <FeedPage tab="trending" />;
}
