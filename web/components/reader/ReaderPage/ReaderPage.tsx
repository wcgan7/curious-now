'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

import styles from './ReaderPage.module.css';
import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';
import { getClusterOffline, saveClusterOffline } from '@/lib/offline/db';
import { getClusterDetailClient } from '@/lib/api/clustersClient';
import { StoryActions } from '@/components/story/StoryActions/StoryActions';
import type { ClusterDetail } from '@/types/api';
import { DeepDive } from '@/components/story/DeepDive/DeepDive';

function toDisplayTitle(takeaway: string | null | undefined, canonicalTitle: string): string {
  if (!takeaway) return canonicalTitle;
  const firstSentence = takeaway.split(/(?<=[.!?])\s+/)[0]?.trim() || takeaway.trim();
  if (firstSentence.length <= 120) return firstSentence;
  return `${firstSentence.slice(0, 119).trimEnd()}…`;
}

function EvidenceList({ cluster }: { cluster: ClusterDetail }) {
  const entries = Object.entries(cluster.evidence || {});
  if (!entries.length) return <p className={styles.hint}>No evidence available.</p>;

  return (
    <div className={styles.evidence}>
      {entries.map(([group, items]) => (
        <section key={group} className={styles.evidenceGroup} aria-labelledby={`evidence-${group}`}>
          <h3 id={`evidence-${group}`} className={styles.h3}>
            {group.replaceAll('_', ' ')}
          </h3>
          <ul className={styles.evidenceList}>
            {items.map((it) => (
              <li key={it.item_id} className={styles.evidenceItem}>
                <a href={it.url} target="_blank" rel="noreferrer" className={styles.evidenceLink}>
                  {it.title}
                </a>
                <div className={styles.meta}>
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
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function ReaderPage() {
  const router = useRouter();
  const params = useSearchParams();
  const id = (params.get('id') || '').trim();
  const { isOnline } = useNetworkStatus();

  const query = useQuery({
    queryKey: ['reader', id, isOnline],
    enabled: Boolean(id),
    queryFn: async () => {
      if (isOnline) {
        const res = await getClusterDetailClient(id);
        if (res.kind === 'redirect') {
          return { kind: 'redirect' as const, toId: res.toId };
        }
        if (res.kind === 'not_found') {
          return { kind: 'not_found' as const };
        }
        await saveClusterOffline(res.cluster);
        return { kind: 'ok' as const, cluster: res.cluster };
      }
      const offline = await getClusterOffline(id);
      if (!offline) return { kind: 'offline_missing' as const };
      return { kind: 'ok' as const, cluster: offline };
    },
    staleTime: isOnline ? 60_000 : Infinity,
  });

  useEffect(() => {
    if (query.data?.kind === 'redirect') {
      router.replace(`/reader?id=${encodeURIComponent(query.data.toId)}`);
    }
  }, [query.data, router]);

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <h1 className={styles.title}>Reader</h1>
            <Link href="/saved" className={styles.back}>
              Back
            </Link>
          </div>
          <p className={styles.subtitle}>
            {isOnline ? 'Online' : 'Offline'} view for a saved story.
          </p>
        </header>

        {!id ? (
          <p className={styles.error}>Missing story id.</p>
        ) : query.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : query.data?.kind === 'not_found' ? (
          <p className={styles.error}>Story not found.</p>
        ) : query.data?.kind === 'offline_missing' ? (
          <div className={styles.missing}>
            <p className={styles.error}>This story isn&apos;t available offline.</p>
            <p className={styles.hint}>Go online and download it from Saved.</p>
            <Link href="/saved" className={styles.link}>
              Go to Saved
            </Link>
          </div>
        ) : query.data?.kind === 'ok' ? (
          <article className={styles.article}>
            <h2 className={styles.storyTitle}>
              {toDisplayTitle(query.data.cluster.takeaway, query.data.cluster.canonical_title)}
            </h2>
            {query.data.cluster.takeaway &&
            toDisplayTitle(query.data.cluster.takeaway, query.data.cluster.canonical_title) !==
              query.data.cluster.canonical_title ? (
              <p className={styles.canonicalTitle}>Paper title: {query.data.cluster.canonical_title}</p>
            ) : null}
            <div className={styles.actionsRow}>
              <StoryActions
                clusterId={query.data.cluster.cluster_id}
                cluster={query.data.cluster}
                initial={{
                  saved: Boolean(query.data.cluster.is_saved) || !isOnline,
                  watched: Boolean(query.data.cluster.is_watched),
                }}
              />
            </div>

            {query.data.cluster.takeaway ? (
              <section className={styles.section}>
                <h3 className={styles.h3}>Takeaway</h3>
                <p className={styles.prose}>{query.data.cluster.takeaway}</p>
              </section>
            ) : null}

            {query.data.cluster.summary_intuition ? (
              <section className={styles.section}>
                <h3 className={styles.h3}>Intuition (ELI5)</h3>
                <p className={styles.prose}>{query.data.cluster.summary_intuition}</p>
                {(
                  query.data.cluster as ClusterDetail & {
                    summary_intuition_eli20?: string | null;
                  }
                ).summary_intuition_eli20 ? (
                  <details className={styles.details}>
                    <summary className={styles.summary}>More technical (ELI20)</summary>
                    <p className={styles.prose}>
                      {
                        (
                          query.data.cluster as ClusterDetail & {
                            summary_intuition_eli20?: string | null;
                          }
                        ).summary_intuition_eli20
                      }
                    </p>
                  </details>
                ) : null}
              </section>
            ) : null}

            {query.data.cluster.summary_deep_dive ? (
              <details className={styles.details}>
                <summary className={styles.summary}>Deep dive</summary>
                <div className={styles.section}>
                  <DeepDive value={query.data.cluster.summary_deep_dive} />
                </div>
              </details>
            ) : null}

            <section className={styles.section} aria-labelledby="evidence-heading">
              <h3 id="evidence-heading" className={styles.h3}>
                Evidence
              </h3>
              <EvidenceList cluster={query.data.cluster} />
            </section>
          </article>
        ) : (
          <p className={styles.error}>Unable to load story.</p>
        )}
      </div>
    </main>
  );
}
