'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ClusterCard } from '@/components/feed/ClusterCard/ClusterCard';
import { getFeedClient } from '@/lib/api/feedClient';
import type { ClusterCard as ClusterCardType } from '@/types/api';

import styles from './FeedPage.module.css';

const PAGE_SIZE = 20;
const MAX_AUTO_PAGES = 30;

export function InfiniteFeedList({
  tab,
  initialItems,
  hasInitialError,
}: {
  tab: 'latest' | 'trending';
  initialItems: ClusterCardType[];
  hasInitialError: boolean;
}) {
  const [items, setItems] = useState<ClusterCardType[]>(initialItems);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(!hasInitialError && initialItems.length === PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const seenIds = useMemo(() => new Set(items.map((item) => item.cluster_id)), [items]);

  const loadNextPage = useCallback(async () => {
    if (isLoading || !hasMore || hasInitialError) return;
    if (page >= MAX_AUTO_PAGES) {
      setHasMore(false);
      return;
    }

    setIsLoading(true);
    setLoadError(null);
    const nextPage = page + 1;

    try {
      const feed = await getFeedClient({
        tab,
        page: nextPage,
        pageSize: PAGE_SIZE,
      });

      const incoming = feed.results.filter((c) => !seenIds.has(c.cluster_id));
      setItems((prev) => [...prev, ...incoming]);
      setPage(nextPage);
      setHasMore(feed.results.length === PAGE_SIZE && nextPage < MAX_AUTO_PAGES);
    } catch {
      setLoadError('Could not load more stories. Scroll to retry.');
    } finally {
      setIsLoading(false);
    }
  }, [hasInitialError, hasMore, isLoading, page, seenIds, tab]);

  useEffect(() => {
    if (!hasMore || hasInitialError) return;
    if (typeof IntersectionObserver === 'undefined') return;
    const node = sentinelRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadNextPage();
        }
      },
      { root: null, rootMargin: '800px 0px 800px 0px', threshold: 0.01 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [hasInitialError, hasMore, loadNextPage]);

  return (
    <>
      <div className={styles.list}>
        {items.map((c) => (
          <ClusterCard key={c.cluster_id} cluster={c} />
        ))}
      </div>

      {hasMore ? <div ref={sentinelRef} className={styles.sentinel} aria-hidden="true" /> : null}
      {hasMore && !isLoading ? (
        <div className={styles.actions}>
          <button type="button" className={styles.loadMoreButton} onClick={() => void loadNextPage()}>
            Load More
          </button>
        </div>
      ) : null}
      {isLoading ? <p className={styles.loadingNotice}>Loading more stories…</p> : null}
      {loadError ? <p className={styles.errorNotice}>{loadError}</p> : null}
      {!hasMore && items.length >= PAGE_SIZE * MAX_AUTO_PAGES ? (
        <p className={styles.emptyNotice}>
          Reached the continuous scroll limit for this session ({PAGE_SIZE * MAX_AUTO_PAGES} stories).
        </p>
      ) : null}
    </>
  );
}
