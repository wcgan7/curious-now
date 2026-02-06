'use client';

import { useMemo, useState } from 'react';

import styles from './IntuitionSection.module.css';
import { SupportingEvidence } from '@/components/story/SupportingEvidence/SupportingEvidence';
import type { ClusterDetail } from '@/types/api';

type ModeId = 'eli5' | 'eli20';

type Mode = {
  id: ModeId;
  label: string;
  text: string;
  supportingItemIds?: string[] | null;
};

function clean(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function IntuitionSection({
  eli5,
  eli20,
  evidence,
  supportingItemIdsEli5,
  supportingItemIdsEli20,
}: {
  eli5?: string | null;
  eli20?: string | null;
  evidence: ClusterDetail['evidence'];
  supportingItemIdsEli5?: string[] | null;
  supportingItemIdsEli20?: string[] | null;
}) {
  const modes = useMemo<Mode[]>(() => {
    const out: Mode[] = [];
    const e5 = clean(eli5);
    const e20 = clean(eli20);

    if (e5) {
      out.push({
        id: 'eli5',
        label: 'ELI5',
        text: e5,
        supportingItemIds: supportingItemIdsEli5,
      });
    }
    if (e20) {
      out.push({
        id: 'eli20',
        label: 'ELI20',
        text: e20,
        supportingItemIds: supportingItemIdsEli20,
      });
    }
    return out;
  }, [eli5, eli20, supportingItemIdsEli5, supportingItemIdsEli20]);

  const [selected, setSelected] = useState<ModeId>(modes[0]?.id ?? 'eli5');
  if (!modes.length) return null;

  const active = modes.find((m) => m.id === selected) ?? modes[0];
  const showToggle = modes.length > 1;

  return (
    <section className={styles.section} aria-labelledby="intuition-heading">
      <div className={styles.headerRow}>
        <h2 id="intuition-heading" className={styles.h2}>
          Intuition
        </h2>
        {showToggle ? (
          <div className={styles.toggle} role="tablist" aria-label="Intuition level">
            {modes.map((mode) => (
              <button
                key={mode.id}
                type="button"
                role="tab"
                aria-selected={active.id === mode.id}
                className={active.id === mode.id ? styles.activeTab : styles.tab}
                onClick={() => setSelected(mode.id)}
              >
                {mode.label}
              </button>
            ))}
          </div>
        ) : (
          <span className={styles.modePill}>{active.label}</span>
        )}
      </div>

      <p className={styles.prose}>{active.text}</p>

      <SupportingEvidence
        label={`Evidence for intuition (${active.label})`}
        itemIds={active.supportingItemIds}
        evidence={evidence}
        onlyPapers={false}
      />
    </section>
  );
}
