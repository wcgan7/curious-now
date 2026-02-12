import Link from 'next/link';

import type { TopicDetail } from '@/types/api';
import { ClusterCard } from '@/components/feed/ClusterCard/ClusterCard';
import { env } from '@/lib/config/env';

import styles from './TopicPage.module.css';

function uniqueByClusterId(clusters: TopicDetail['latest_clusters']) {
  const seen = new Set<string>();
  return clusters.filter((cluster) => {
    if (seen.has(cluster.cluster_id)) return false;
    seen.add(cluster.cluster_id);
    return true;
  });
}

export function TopicPage({ detail }: { detail: TopicDetail }) {
  const topic = detail.topic;
  const topicType = topic.topic_type;
  const isCategory = topicType === 'category';
  const focusCategory = isCategory ? { categoryId: topic.topic_id, name: topic.name } : undefined;
  const latestClusters = uniqueByClusterId(detail.latest_clusters);
  const trendingClusters = uniqueByClusterId(detail.trending_clusters ?? []);

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <div className={styles.titleBlock}>
              <h1 className={styles.title}>{topic.name}</h1>
              {topic.description_short ? (
                <p className={styles.subtitle}>{topic.description_short}</p>
              ) : null}
            </div>
          </div>

          <div className={styles.links}>
            <Link className={styles.link} href={`/search?q=${encodeURIComponent(topic.name)}`}>
              Search related
            </Link>
            {env.features.lineage && !isCategory ? (
              <Link className={styles.link} href={`/topic/${topic.topic_id}/lineage`}>
                Lineage
              </Link>
            ) : null}
          </div>
        </header>

        <section className={styles.section} aria-labelledby="latest-heading">
          <h2 id="latest-heading" className={styles.h2}>
            Latest
          </h2>
          <div className={styles.list}>
            {latestClusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c} focusCategory={focusCategory} />
            ))}
          </div>
        </section>

        {trendingClusters.length ? (
          <section className={styles.section} aria-labelledby="trending-heading">
            <h2 id="trending-heading" className={styles.h2}>
              {isCategory ? 'Trending in this category' : 'Trending in this topic'}
            </h2>
            <div className={styles.list}>
              {trendingClusters.map((c) => (
                <ClusterCard key={c.cluster_id} cluster={c} focusCategory={focusCategory} />
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
