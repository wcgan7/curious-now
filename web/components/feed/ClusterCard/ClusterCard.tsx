import { formatDistanceToNow } from 'date-fns';

import type { ClusterCard as ClusterCardType } from '@/types/api';
import { Card } from '@/components/ui/Card/Card';
import { Badge } from '@/components/ui/Badge/Badge';

import styles from './ClusterCard.module.css';

type FocusCategory = {
  categoryId: string;
  name: string;
};

export function ClusterCard({
  cluster,
  focusCategory,
}: {
  cluster: ClusterCardType;
  focusCategory?: FocusCategory;
}) {
  const topCategories = cluster.top_categories || [];
  const matchedFocusCategory = focusCategory
    ? topCategories.find(
        (category) =>
          category.category_id === focusCategory.categoryId ||
          category.name.toLowerCase() === focusCategory.name.toLowerCase()
      )
    : null;
  const primaryCategory = matchedFocusCategory ?? topCategories[0];
  const categoryNameSet = new Set([primaryCategory?.name.toLowerCase()].filter(Boolean));
  const topSubtopics = (cluster.top_topics || [])
    .filter((topic) => !categoryNameSet.has(topic.name.toLowerCase()))
    .slice(0, 2);
  const sourceTypeBadges = cluster.content_type_badges || [];
  const showHighImpact = Boolean(cluster.high_impact_label);

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
        {topCategories.length || topSubtopics.length || showHighImpact ? (
          <div className={styles.metaRow}>
            <div className={styles.badges}>
              {primaryCategory ? <Badge variant="info">{primaryCategory.name}</Badge> : null}
              {topSubtopics.map((topic) => (
                <Badge key={topic.topic_id}>{topic.name}</Badge>
              ))}
              {showHighImpact ? <Badge variant="warning">High Impact</Badge> : null}
            </div>
          </div>
        ) : null}

        <Card.Title>{cluster.canonical_title}</Card.Title>

        {cluster.takeaway ? <p className={styles.takeaway}>{cluster.takeaway}</p> : null}

        {sourceTypeBadges.length ? (
          <div className={styles.sourceTypes} aria-label="Source types">
            {sourceTypeBadges.slice(0, 2).map((type) => (
              <span key={type} className={styles.sourceType}>
                {type.replace(/_/g, ' ')}
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
