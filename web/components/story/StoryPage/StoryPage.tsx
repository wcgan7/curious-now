'use client';

import Link from 'next/link';

import type { ClusterDetail } from '@/types/api';

import styles from './StoryPage.module.css';
import { TakeawayModule } from '@/components/story/TakeawayModule/TakeawayModule';
import { TrustBox } from '@/components/story/TrustBox/TrustBox';
import { EvidencePanel } from '@/components/story/EvidencePanel/EvidencePanel';
import { StoryActions } from '@/components/story/StoryActions/StoryActions';
import { DeepDive } from '@/components/story/DeepDive/DeepDive';
import { IntuitionSection } from '@/components/story/IntuitionSection/IntuitionSection';

function parseDeepDivePayload(
  summaryDeepDive: string | null | undefined
): { markdown?: string; eli5?: string; eli20?: string } {
  if (!summaryDeepDive) return {};
  const text = summaryDeepDive.trim();
  if (!(text.startsWith('{') && text.endsWith('}'))) return {};

  try {
    const parsed = JSON.parse(text) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const obj = parsed as Record<string, unknown>;

    return {
      markdown: typeof obj.markdown === 'string' ? obj.markdown : undefined,
      eli5: typeof obj.eli5 === 'string' ? obj.eli5 : undefined,
      eli20: typeof obj.eli20 === 'string' ? obj.eli20 : undefined,
    };
  } catch {
    return {};
  }
}

function hasText(value: string | null | undefined): boolean {
  return typeof value === 'string' && value.trim().length > 0;
}

export function StoryPage({
  cluster,
  hasUpdates = false,
}: {
  cluster: ClusterDetail;
  hasUpdates?: boolean;
}) {
  const extended = cluster as ClusterDetail & {
    summary_intuition_eli5?: string | null;
    summary_intuition_eli20?: string | null;
    summary_intuition_eli5_supporting_item_ids?: string[] | null;
    summary_intuition_eli20_supporting_item_ids?: string[] | null;
  };
  const deepDivePayload = parseDeepDivePayload(cluster.summary_deep_dive);
  const eli5 =
    extended.summary_intuition_eli5 ?? cluster.summary_intuition ?? deepDivePayload.eli5 ?? null;
  const eli20 = extended.summary_intuition_eli20 ?? deepDivePayload.eli20 ?? null;
  const eli5SupportingIds =
    extended.summary_intuition_eli5_supporting_item_ids ??
    cluster.summary_intuition_supporting_item_ids;
  const eli20SupportingIds =
    extended.summary_intuition_eli20_supporting_item_ids ??
    cluster.summary_intuition_supporting_item_ids;
  const hasTakeaway = hasText(cluster.takeaway);
  const hasIntuition = hasText(eli5) || hasText(eli20);
  const hasDeepDive = hasText(cluster.summary_deep_dive);
  const hasContextLists =
    !!cluster.assumptions?.length ||
    !!cluster.limitations?.length ||
    !!cluster.what_could_change_this?.length;
  const sections = [
    ...(hasTakeaway || hasContextLists ? [{ id: 'overview', label: 'Overview' }] : []),
    ...(hasIntuition ? [{ id: 'intuition', label: 'Intuition' }] : []),
    ...(hasDeepDive ? [{ id: 'deep-dive', label: 'Deep Dive' }] : []),
    { id: 'evidence', label: 'Evidence' },
  ];

  return (
    <main className={styles.main}>
      <article className={styles.container}>
        <header className={styles.hero}>
          <div className={styles.heroTop}>
            <p className={styles.eyebrow}>Story</p>
            <h1 className={styles.title}>{cluster.canonical_title}</h1>
            <div className={styles.heroMeta}>
              {cluster.distinct_source_count > 1 ? (
                <span className={styles.metaChip}>
                  {cluster.distinct_source_count} sources
                </span>
              ) : null}
              {hasUpdates ? (
                <Link href={`/story/${cluster.cluster_id}/updates`} className={styles.updatesLink}>
                  View updates
                </Link>
              ) : null}
            </div>
          </div>
          {hasTakeaway ? (
            <div className={styles.heroTakeaway}>
              <p className={styles.takeawayLabel}>Key takeaway</p>
              <p className={styles.takeawayText}>{cluster.takeaway}</p>
            </div>
          ) : null}
          <div className={styles.actionsRow}>
            <StoryActions
              clusterId={cluster.cluster_id}
              cluster={cluster}
              initial={{ saved: !!cluster.is_saved, watched: !!cluster.is_watched }}
            />
          </div>
        </header>

        <div className={styles.columns}>
          <section className={styles.content}>
            <nav className={styles.tabNav} aria-label="Story sections">
              {sections.map((section) => (
                <a key={section.id} className={styles.tabLink} href={`#${section.id}`}>
                  {section.label}
                </a>
              ))}
            </nav>

            {hasTakeaway || hasContextLists ? (
              <section id="overview" className={styles.panel}>
                <h2 className={styles.h2}>Overview</h2>
                {hasTakeaway ? (
                  <div className={styles.block}>
                    <TakeawayModule takeaway={cluster.takeaway as string} />
                  </div>
                ) : null}

                {cluster.assumptions?.length ? (
                  <div className={styles.listBlock}>
                    <h3 className={styles.h3}>Assumptions</h3>
                    <ul className={styles.list}>
                      {cluster.assumptions.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {cluster.limitations?.length ? (
                  <div className={styles.listBlock}>
                    <h3 className={styles.h3}>Limitations</h3>
                    <ul className={styles.list}>
                      {cluster.limitations.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {cluster.what_could_change_this?.length ? (
                  <div className={styles.listBlock}>
                    <h3 className={styles.h3}>What could change this</h3>
                    <ul className={styles.list}>
                      {cluster.what_could_change_this.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </section>
            ) : null}

            {hasIntuition ? (
              <section id="intuition" className={styles.panel}>
                <IntuitionSection
                  eli5={eli5}
                  eli20={eli20}
                  evidence={cluster.evidence}
                  supportingItemIdsEli5={eli5SupportingIds}
                  supportingItemIdsEli20={eli20SupportingIds}
                  showEvidence={false}
                />
              </section>
            ) : null}

            {hasDeepDive ? (
              <section id="deep-dive" className={styles.panel}>
                <div className={styles.section}>
                  <h2 className={styles.h2}>Deep dive</h2>
                  <DeepDive value={deepDivePayload.markdown ?? cluster.summary_deep_dive!} />
                </div>
              </section>
            ) : null}

            <section id="evidence" className={styles.panel}>
              <h2 className={styles.h2}>Evidence</h2>
              <div className={styles.section}>
                <EvidencePanel evidence={cluster.evidence} />
              </div>
            </section>
          </section>

          <aside className={styles.sidebar}>
            <div className={styles.rail}>
              <TrustBox
                contentTypeBreakdown={cluster.content_type_breakdown || {}}
                distinctSourceCount={cluster.distinct_source_count}
                confidenceBand={cluster.confidence_band}
                methodBadges={cluster.method_badges || []}
                antiHypeFlags={cluster.anti_hype_flags || []}
              />
              <div className={styles.quickNav}>
                <p className={styles.quickNavLabel}>Quick jump</p>
                <div className={styles.quickNavButtons}>
                  {sections.map((section) => (
                    <a
                      key={`quick-${section.id}`}
                      className={styles.quickLink}
                      href={`#${section.id}`}
                    >
                      {section.label}
                    </a>
                  ))}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </article>
    </main>
  );
}
