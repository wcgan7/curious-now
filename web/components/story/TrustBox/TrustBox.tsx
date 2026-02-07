import { Badge } from '@/components/ui/Badge/Badge';

import styles from './TrustBox.module.css';

export function TrustBox({
  contentTypeBreakdown,
  distinctSourceCount,
  confidenceBand,
  methodBadges,
  antiHypeFlags,
  sticky = true,
}: {
  contentTypeBreakdown: Record<string, number>;
  distinctSourceCount: number;
  confidenceBand?: 'early' | 'growing' | 'established' | null;
  methodBadges: string[];
  antiHypeFlags: string[];
  sticky?: boolean;
}) {
  const isSingleSource = distinctSourceCount <= 1;
  const confidenceLabels: Record<string, string> = {
    early: 'Early — limited evidence, may change significantly',
    growing: 'Growing — multiple sources, gaining clarity',
    established: 'Established — consistent reporting over time',
  };

  return (
    <aside
      className={`${styles.box} ${sticky ? styles.sticky : ''}`}
      aria-labelledby={isSingleSource ? undefined : 'trust-heading'}
      aria-label={isSingleSource ? 'Source details' : undefined}
    >
      {!isSingleSource ? (
        <h2 id="trust-heading" className={styles.heading}>
          Source summary
        </h2>
      ) : null}

      {confidenceBand ? (
        <div className={styles.row}>
          <span className={styles.label}>Confidence</span>
          <span className={styles.value}>{confidenceLabels[confidenceBand]}</span>
        </div>
      ) : null}

      {distinctSourceCount > 1 ? (
        <div className={styles.row}>
          <span className={styles.label}>Independent sources</span>
          <span className={styles.value}>{distinctSourceCount}</span>
        </div>
      ) : null}

      {!isSingleSource ? (
        <div className={styles.block}>
          <span className={styles.label}>Source types</span>
          <div className={styles.tags}>
            {Object.entries(contentTypeBreakdown)
              .filter(([, count]) => count > 0)
              .map(([type, count]) => (
                <Badge key={type}>{`${type.replace(/_/g, ' ')} · ${count}`}</Badge>
              ))}
          </div>
        </div>
      ) : null}

      {methodBadges.length ? (
        <div className={styles.block}>
          <span className={styles.label}>Method</span>
          <div className={styles.tags}>
            {methodBadges.map((b) => (
              <Badge key={b}>{b.replace(/_/g, ' ')}</Badge>
            ))}
          </div>
        </div>
      ) : null}

      {antiHypeFlags.length ? (
        <div className={styles.block}>
          <span className={styles.label}>Notes</span>
          <div className={styles.tags}>
            {antiHypeFlags.slice(0, 6).map((b) => (
              <Badge key={b} variant="warning">
                {b.replace(/_/g, ' ')}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
