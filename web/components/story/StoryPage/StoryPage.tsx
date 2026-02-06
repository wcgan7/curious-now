import type { ClusterDetail } from '@/types/api';

import styles from './StoryPage.module.css';
import { TakeawayModule } from '@/components/story/TakeawayModule/TakeawayModule';
import { TrustBox } from '@/components/story/TrustBox/TrustBox';
import { EvidencePanel } from '@/components/story/EvidencePanel/EvidencePanel';
import { StoryActions } from '@/components/story/StoryActions/StoryActions';
import { SupportingEvidence } from '@/components/story/SupportingEvidence/SupportingEvidence';
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

export function StoryPage({ cluster }: { cluster: ClusterDetail }) {
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

  return (
    <main className={styles.main}>
      <article className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.title}>{cluster.canonical_title}</h1>
          <div className={styles.actionsRow}>
            <StoryActions
              clusterId={cluster.cluster_id}
              cluster={cluster}
              initial={{ saved: !!cluster.is_saved, watched: !!cluster.is_watched }}
            />
          </div>
        </header>

        {cluster.takeaway ? (
          <div className={styles.block}>
            <TakeawayModule takeaway={cluster.takeaway} />
            <SupportingEvidence
              label="Evidence for takeaway"
              itemIds={cluster.takeaway_supporting_item_ids}
              evidence={cluster.evidence}
              onlyPapers={false}
            />
          </div>
        ) : null}

        <div className={styles.columns}>
          <section className={styles.content}>
            {eli5 || eli20 ? (
              <IntuitionSection
                eli5={eli5}
                eli20={eli20}
                evidence={cluster.evidence}
                supportingItemIdsEli5={eli5SupportingIds}
                supportingItemIdsEli20={eli20SupportingIds}
              />
            ) : null}

            {cluster.summary_deep_dive ? (
              <details className={styles.details}>
                <summary className={styles.summary}>Deep dive (papers)</summary>
                <div className={styles.section}>
                  <DeepDive value={deepDivePayload.markdown ?? cluster.summary_deep_dive} />
                  <SupportingEvidence
                    label="Papers used"
                    itemIds={cluster.summary_deep_dive_supporting_item_ids}
                    evidence={cluster.evidence}
                    onlyPapers
                  />

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
                </div>
              </details>
            ) : null}

            <EvidencePanel evidence={cluster.evidence} />
          </section>

          <aside className={styles.sidebar}>
            <TrustBox
              contentTypeBreakdown={cluster.content_type_breakdown || {}}
              distinctSourceCount={cluster.distinct_source_count}
              confidenceBand={cluster.confidence_band}
              methodBadges={cluster.method_badges || []}
              antiHypeFlags={cluster.anti_hype_flags || []}
            />
          </aside>
        </div>
      </article>
    </main>
  );
}
