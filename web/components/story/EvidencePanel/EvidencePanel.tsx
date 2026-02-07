'use client';

import { useMemo, useState } from 'react';

import styles from './EvidencePanel.module.css';
import type { ClusterDetail } from '@/types/api';

type Evidence = ClusterDetail['evidence'];
type EvidenceFilter = 'all' | 'news' | 'press_release' | 'preprint' | 'peer_reviewed' | 'report';
type SortMode = 'newest' | 'oldest';

type EvidenceItemWithType = NonNullable<Evidence[string]>[number] & {
  contentType: Exclude<EvidenceFilter, 'all'>;
};

const LABELS: Record<Exclude<EvidenceFilter, 'all'>, string> = {
  peer_reviewed: 'Peer-reviewed',
  preprint: 'Preprint',
  report: 'Report',
  press_release: 'Press release',
  news: 'News',
};

function toItems(evidence: Evidence): EvidenceItemWithType[] {
  const out: EvidenceItemWithType[] = [];
  for (const [contentType, items] of Object.entries(evidence || {})) {
    const ct = contentType as Exclude<EvidenceFilter, 'all'>;
    for (const it of items || []) out.push({ ...it, contentType: ct });
  }
  return out;
}

function byDate(mode: SortMode) {
  return (a: EvidenceItemWithType, b: EvidenceItemWithType) => {
    const aTime = a.published_at ? Date.parse(a.published_at) : Number.NEGATIVE_INFINITY;
    const bTime = b.published_at ? Date.parse(b.published_at) : Number.NEGATIVE_INFINITY;
    return mode === 'newest' ? bTime - aTime : aTime - bTime;
  };
}

function EvidenceList({
  label,
  items,
}: {
  label?: string;
  items: EvidenceItemWithType[];
}) {
  if (!items.length) return null;
  return (
    <section className={styles.group} aria-label={label || 'Source list'}>
      {label ? <h3 className={styles.groupHeading}>{label}</h3> : null}
      <ul className={styles.list}>
        {items.map((it) => (
          <li key={it.item_id} className={styles.item}>
            <div className={styles.itemContent}>
              {it.image_url ? (
                <img
                  src={it.image_url}
                  alt=""
                  className={styles.thumb}
                  loading="lazy"
                />
              ) : null}
              <div className={styles.itemText}>
                <a href={it.url} target="_blank" rel="noreferrer" className={styles.link}>
                  {it.title}
                </a>
                <div className={styles.meta}>
                  <span className={styles.typeBadge}>{LABELS[it.contentType] || it.contentType}</span>
                  <span>{it.source.name}</span>
                  {it.published_at ? (
                    <>
                      <span aria-hidden="true">&middot;</span>
                      <time dateTime={it.published_at}>
                        {new Date(it.published_at).toLocaleDateString()}
                      </time>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function EvidencePanel({
  evidence,
  selectedType = 'all',
  onSelectType,
  relevantItemIds = [],
  isSingleSource = false,
}: {
  evidence: Evidence;
  selectedType?: EvidenceFilter;
  onSelectType?: (next: EvidenceFilter) => void;
  relevantItemIds?: string[];
  isSingleSource?: boolean;
}) {
  const [sortMode, setSortMode] = useState<SortMode>('newest');
  const items = useMemo(() => toItems(evidence), [evidence]);
  const relevantSet = useMemo(() => new Set(relevantItemIds), [relevantItemIds]);

  const visible = useMemo(() => {
    const filtered =
      selectedType === 'all' ? items : items.filter((it) => it.contentType === selectedType);
    return [...filtered].sort(byDate(sortMode));
  }, [items, selectedType, sortMode]);

  const prioritized = useMemo(
    () => visible.filter((it) => relevantSet.has(it.item_id)),
    [visible, relevantSet]
  );
  const additional = useMemo(
    () => visible.filter((it) => !relevantSet.has(it.item_id)),
    [visible, relevantSet]
  );
  const flatSingleSourceItems = useMemo(() => [...items].sort(byDate('newest')), [items]);

  return (
    <section className={styles.panel} aria-label="Source details">
      {!isSingleSource ? (
        <div className={styles.headerRow}>
          <div className={styles.filters} role="tablist" aria-label="Source type">
            <button
              type="button"
              role="tab"
              aria-selected={selectedType === 'all'}
              className={selectedType === 'all' ? styles.activeFilter : styles.filter}
              onClick={() => onSelectType?.('all')}
            >
              All
            </button>
            {(Object.keys(LABELS) as Array<Exclude<EvidenceFilter, 'all'>>)
              .filter((type) => items.some((it) => it.contentType === type))
              .map((type) => (
                <button
                  key={type}
                  type="button"
                  role="tab"
                  aria-selected={selectedType === type}
                  className={selectedType === type ? styles.activeFilter : styles.filter}
                  onClick={() => onSelectType?.(type)}
                >
                  {LABELS[type]}
                </button>
              ))}
          </div>
          <div className={styles.controls}>
            <label className={styles.controlLabel}>
              Sort
              <select
                className={styles.select}
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
              >
                <option value="newest">Most recent</option>
                <option value="oldest">Oldest</option>
              </select>
            </label>
          </div>
        </div>
      ) : null}

      <div className={styles.groups}>
        {isSingleSource ? (
          <EvidenceList items={flatSingleSourceItems} />
        ) : (
          <>
            <EvidenceList label="Most relevant to this story" items={prioritized} />
            <EvidenceList label="Additional sources" items={additional} />
          </>
        )}
      </div>
    </section>
  );
}
