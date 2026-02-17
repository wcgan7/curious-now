import styles from './SupportingEvidence.module.css';
import type { ClusterDetail } from '@/types/api';

type Evidence = ClusterDetail['evidence'];

type EvidenceItem = NonNullable<Evidence>[string][number];

const PAPER_TYPES = new Set(['peer_reviewed', 'preprint', 'report']);

function flattenEvidence(evidence: Evidence): Map<string, { item: EvidenceItem; group: string }> {
  const map = new Map<string, { item: EvidenceItem; group: string }>();
  for (const [group, items] of Object.entries(evidence || {})) {
    for (const item of items) {
      map.set(item.item_id, { item, group });
    }
  }
  return map;
}

export function SupportingEvidence({
  label = 'Supporting sources',
  itemIds,
  evidence,
  onlyPapers = false,
}: {
  label?: string;
  itemIds: string[] | undefined | null;
  evidence: Evidence;
  onlyPapers?: boolean;
}) {
  const ids = (itemIds || []).filter(Boolean);
  if (!ids.length) return null;

  const map = flattenEvidence(evidence);
  const items = ids
    .map((id) => map.get(id))
    .filter(Boolean)
    .map((x) => x!);

  const filtered = onlyPapers
    ? items.filter((x) => PAPER_TYPES.has(x.item.content_type || x.group))
    : items;

  if (!filtered.length) return null;

  return (
    <section className={styles.wrap} aria-label={label}>
      <h3 className={styles.heading}>{label}</h3>
      <ul className={styles.list}>
        {filtered.map(({ item }) => (
          <li key={item.item_id} className={styles.item}>
            <a href={item.url} target="_blank" rel="noopener noreferrer" className={styles.link}>
              {item.title}
            </a>
            <div className={styles.meta}>
              <span>{item.source.name}</span>
              {item.published_at ? (
                <>
                  <span aria-hidden="true">&middot;</span>
                  <time dateTime={item.published_at}>
                    {new Date(item.published_at).toLocaleDateString()}
                  </time>
                </>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
