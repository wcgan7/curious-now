import styles from './EvidencePanel.module.css';
import type { ClusterDetail } from '@/types/api';

type Evidence = ClusterDetail['evidence'];

const LABELS: Record<string, string> = {
  peer_reviewed: 'Peer-reviewed',
  preprint: 'Preprint',
  report: 'Report',
  press_release: 'Press release',
  news: 'News',
};

export function EvidencePanel({ evidence }: { evidence: Evidence }) {
  const entries = Object.entries(evidence || {}).filter(([, items]) => items.length > 0);
  return (
    <section className={styles.panel} aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className={styles.heading}>
        Evidence
      </h2>

      <div className={styles.groups}>
        {entries.map(([contentType, items]) => (
          <section key={contentType} className={styles.group} aria-label={contentType}>
            <h3 className={styles.groupHeading}>{LABELS[contentType] || contentType}</h3>
            <ul className={styles.list}>
              {items.map((it) => (
                <li key={it.item_id} className={styles.item}>
                  <a href={it.url} target="_blank" rel="noreferrer" className={styles.link}>
                    {it.title}
                  </a>
                  <div className={styles.meta}>
                    <span>{it.source.name}</span>
                    {it.published_at ? (
                      <>
                        <span aria-hidden="true">&middot;</span>
                        <time dateTime={it.published_at}>{new Date(it.published_at).toLocaleDateString()}</time>
                      </>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </section>
  );
}

