import Link from 'next/link';

import type { TopicDetail } from '@/types/api';
import { ClusterCard } from '@/components/feed/ClusterCard/ClusterCard';
import { env } from '@/lib/config/env';

import styles from './TopicPage.module.css';

export function TopicPage({ detail }: { detail: TopicDetail }) {
  const topic = detail.topic;
  const topicType = topic.topic_type;
  const isCategory = topicType === 'category';

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
            {detail.latest_clusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c} />
            ))}
          </div>
        </section>

        {detail.trending_clusters?.length ? (
          <section className={styles.section} aria-labelledby="trending-heading">
            <h2 id="trending-heading" className={styles.h2}>
              {isCategory ? 'Trending in this category' : 'Trending in this topic'}
            </h2>
            <div className={styles.list}>
              {detail.trending_clusters.map((c) => (
                <ClusterCard key={c.cluster_id} cluster={c} />
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
