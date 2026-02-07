import { formatDistanceToNow } from 'date-fns';

import type { ClusterCard as ClusterCardType } from '@/types/api';
import { Card } from '@/components/ui/Card/Card';
import { Badge } from '@/components/ui/Badge/Badge';

import styles from './ClusterCard.module.css';

export function ClusterCard({ cluster }: { cluster: ClusterCardType }) {
  const topCategories = cluster.top_categories || [];
  const categoryNameSet = new Set(topCategories.map((c) => c.name.toLowerCase()));
  const topSubtopics = (cluster.top_topics || [])
    .filter((topic) => !categoryNameSet.has(topic.name.toLowerCase()))
    .slice(0, 2);

  return (
    <Card as="article" href={`/story/${cluster.cluster_id}`}>
      {cluster.featured_image_url ? (
        <div className={styles.imageWrapper}>
          <img
            src={cluster.featured_image_url}
            alt=""
            className={styles.image}
            loading="lazy"
          />
        </div>
      ) : null}
      <Card.Content>
        {topCategories.length || topSubtopics.length || cluster.confidence_band ? (
          <div className={styles.metaRow}>
            <div className={styles.badges}>
              {topCategories.slice(0, 1).map((category) => (
                <Badge key={category.category_id} variant="info">
                  {category.name}
                </Badge>
              ))}
              {topSubtopics.map((topic) => (
                <Badge key={topic.topic_id}>{topic.name}</Badge>
              ))}
              {cluster.confidence_band ? <Badge>{cluster.confidence_band}</Badge> : null}
            </div>
          </div>
        ) : null}

        <Card.Title>{cluster.canonical_title}</Card.Title>

        {cluster.takeaway ? <p className={styles.takeaway}>{cluster.takeaway}</p> : null}

        {cluster.anti_hype_flags?.length ? (
          <div className={styles.flags} aria-label="Anti-hype flags">
            {cluster.anti_hype_flags.slice(0, 2).map((flag) => (
              <span key={flag} className={styles.flag}>
                {flag.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        ) : null}

        <Card.Meta>
          <time dateTime={cluster.updated_at}>
            {formatDistanceToNow(new Date(cluster.updated_at), { addSuffix: true })}
          </time>
          <span className={styles.spacer} />
          <span className={styles.readLink} aria-hidden="true">
            Read
          </span>
        </Card.Meta>
      </Card.Content>
    </Card>
  );
}
