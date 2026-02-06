import { formatDistanceToNow } from 'date-fns';

import type { ClusterCard as ClusterCardType } from '@/types/api';
import { Card } from '@/components/ui/Card/Card';
import { ContentTypeBadge, Badge } from '@/components/ui/Badge/Badge';

import styles from './ClusterCard.module.css';

export function ClusterCard({ cluster }: { cluster: ClusterCardType }) {
  return (
    <Card as="article" href={`/story/${cluster.cluster_id}`}>
      <Card.Content>
        <div className={styles.metaRow}>
          <div className={styles.badges}>
            {(cluster.content_type_badges || []).map((ct) => (
              <ContentTypeBadge key={ct} type={ct} />
            ))}
            {cluster.confidence_band ? <Badge>{cluster.confidence_band}</Badge> : null}
          </div>
        </div>

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
          <span>{cluster.distinct_source_count} sources</span>
          <span aria-hidden="true">&middot;</span>
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
