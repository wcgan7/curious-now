'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import type { ClusterDetail } from '@/types/api';

import styles from './StoryPage.module.css';
import { EvidencePanel } from '@/components/story/EvidencePanel/EvidencePanel';
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

function pickPrimarySource(
  evidence: ClusterDetail['evidence'] | null | undefined
): { url: string; title: string; contentType?: string } | null {
  if (!evidence) return null;
  const items = Object.values(evidence).flat();
  if (!items.length) return null;

  const sorted = [...items].sort((a, b) => {
    const aTime = a.published_at ? Date.parse(a.published_at) : Number.NEGATIVE_INFINITY;
    const bTime = b.published_at ? Date.parse(b.published_at) : Number.NEGATIVE_INFINITY;
    return bTime - aTime;
  });
  const item = sorted[0];
  return item?.url ? { url: item.url, title: item.title, contentType: item.content_type } : null;
}

function sourceCtaLabel(contentType: string | undefined): string {
  if (contentType === 'preprint' || contentType === 'peer_reviewed') return 'Read the paper';
  if (contentType === 'report') return 'Read the report';
  if (contentType === 'press_release') return 'Read the press release';
  if (contentType === 'news') return 'Read the article';
  return 'Read the source';
}

type EvidenceFilter = 'all' | 'news' | 'press_release' | 'preprint' | 'peer_reviewed' | 'report';

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
    categories?: { category_id: string; name: string; score: number }[];
    top_categories?: { category_id: string; name: string; score: number }[];
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
  const primarySource = pickPrimarySource(cluster.evidence);
  const isSingleSource = cluster.distinct_source_count === 1;
  const canOpenSourceDirectly = cluster.distinct_source_count === 1 && !!primarySource;
  const directSourceLabel = sourceCtaLabel(primarySource?.contentType);
  const categoryChips = (extended.categories ?? extended.top_categories ?? []).slice(0, 2);
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>('all');
  const relevantItemIds = useMemo(
    () => [
      ...(cluster.takeaway_supporting_item_ids || []),
      ...(cluster.summary_intuition_supporting_item_ids || []),
      ...(cluster.summary_deep_dive_supporting_item_ids || []),
    ],
    [
      cluster.takeaway_supporting_item_ids,
      cluster.summary_intuition_supporting_item_ids,
      cluster.summary_deep_dive_supporting_item_ids,
    ]
  );

  const sections = [
    ...(hasContextLists ? [{ id: 'overview', label: 'Overview' }] : []),
    ...(hasIntuition ? [{ id: 'intuition', label: 'Quick Explainer' }] : []),
    ...(hasDeepDive ? [{ id: 'deep-dive', label: 'Deep Dive' }] : []),
    { id: 'evidence', label: isSingleSource ? 'Source' : 'Sources' },
  ];

  return (
    <main className={styles.main}>
      <article className={styles.container}>
        <header className={styles.hero}>
          {cluster.featured_image_url ? (
            <div className={styles.heroImage}>
              <img
                src={cluster.featured_image_url}
                alt=""
                className={styles.heroImg}
                loading="eager"
              />
            </div>
          ) : null}
          <div className={styles.heroTop}>
            <p className={styles.eyebrow}>Story</p>
            <h1 className={styles.title}>{cluster.canonical_title}</h1>
            <div className={styles.heroMeta}>
              {categoryChips.map((category) => (
                <span key={category.category_id} className={`${styles.metaChip} ${styles.categoryChip}`}>
                  {category.name}
                </span>
              ))}
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
          {canOpenSourceDirectly ? (
            <div className={styles.actionsRow}>
              <a
                href={primarySource.url}
                className={styles.sourceCta}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${directSourceLabel}: ${primarySource.title}`}
              >
                {directSourceLabel}
              </a>
            </div>
          ) : null}
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

            {hasContextLists ? (
              <section id="overview" className={styles.panel}>
                <h2 className={styles.h2}>Overview</h2>
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
                  <h2 className={styles.h2}>Deep Dive</h2>
                  <DeepDive value={deepDivePayload.markdown ?? cluster.summary_deep_dive!} />
                </div>
              </section>
            ) : null}

            <section id="evidence" className={styles.panel}>
              <h2 className={styles.h2}>{isSingleSource ? 'Source' : 'Sources'}</h2>
              <div className={`${styles.section} ${styles.evidenceSection}`}>
                <EvidencePanel
                  evidence={cluster.evidence}
                  selectedType={evidenceFilter}
                  onSelectType={setEvidenceFilter}
                  relevantItemIds={relevantItemIds}
                  isSingleSource={isSingleSource}
                />
              </div>
            </section>
          </section>

          <aside className={styles.sidebar}>
            <div className={styles.rail}>
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
