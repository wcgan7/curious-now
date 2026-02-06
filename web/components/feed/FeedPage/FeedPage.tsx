import { redirect } from 'next/navigation';

import { getFeed } from '@/lib/api/feed';
import { env } from '@/lib/config/env';
import type { ClustersFeedResponse } from '@/types/api';
import { ClusterCard } from '@/components/feed/ClusterCard/ClusterCard';

import styles from './FeedPage.module.css';

export async function FeedPage({
  tab,
  requireAuth = false,
}: {
  tab: 'latest' | 'trending' | 'for_you';
  requireAuth?: boolean;
}) {
  if (tab === 'for_you' && !env.features.forYou) {
    redirect('/');
  }

  let feed: ClustersFeedResponse;
  try {
    feed = await getFeed({ tab });
  } catch (e: any) {
    if ((e as any)?.status === 401 || String(e?.message) === 'unauthorized') {
      if (requireAuth) {
        const dest = tab === 'for_you' ? '/for-you' : '/';
        redirect(`/auth/login?redirect=${encodeURIComponent(dest)}`);
      }
    }
    throw e;
  }

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <p className={styles.kicker}>Curious Now</p>
          <h1 className={styles.title}>
            {tab === 'latest' ? 'Latest' : tab === 'trending' ? 'Trending' : 'For you'}
          </h1>
          <p className={styles.subtitle}>
            {tab === 'latest'
              ? 'Recent science stories, grouped and explained without noise.'
              : tab === 'trending'
                ? 'What readers are exploring right now, with context before hype.'
                : 'Your feed based on followed topics and saved interests.'}
          </p>
        </header>
        <div className={styles.list}>
          {feed.results.map((c) => (
            <ClusterCard key={c.cluster_id} cluster={c} />
          ))}
        </div>
      </div>
    </main>
  );
}
