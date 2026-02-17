import { getFeed } from '@/lib/api/feed';
import type { ClustersFeedResponse } from '@/types/api';
import { InfiniteFeedList } from '@/components/feed/FeedPage/InfiniteFeedList';

import styles from './FeedPage.module.css';

export async function FeedPage({
  tab,
}: {
  tab: 'latest' | 'trending';
}) {
  let feed: ClustersFeedResponse | null = null;
  let hasFeedError = false;
  try {
    feed = await getFeed({ tab });
  } catch {
    hasFeedError = true;
  }

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <p className={styles.kicker}>Curious Now</p>
          <h1 className={styles.title}>
            {tab === 'latest' ? 'Latest' : 'In Focus'}
          </h1>
          <p className={styles.subtitle}>
            {tab === 'latest'
              ? "What's new in science"
              : 'Top stories to watch now'}
          </p>
        </header>
        {hasFeedError ? (
          <p className={styles.errorNotice}>
            Couldn&apos;t load the feed right now. Please refresh in a moment.
          </p>
        ) : null}
        {!hasFeedError && feed && feed.results.length === 0 ? (
          <p className={styles.emptyNotice}>No stories available yet.</p>
        ) : null}
        <InfiniteFeedList
          tab={tab}
          initialItems={feed?.results ?? []}
          hasInitialError={hasFeedError}
        />
      </div>
    </main>
  );
}
