'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

import styles from './SearchPage.module.css';
import { Input } from '@/components/ui/Input/Input';
import { Button } from '@/components/ui/Button/Button';
import { search } from '@/lib/api/search';
import { ClusterCard } from '@/components/feed/ClusterCard/ClusterCard';
import { EmptySearch } from '@/components/search/EmptySearch/EmptySearch';

export function SearchPage() {
  const router = useRouter();
  const params = useSearchParams();
  const qFromUrl = (params.get('q') || '').trim();
  const [q, setQ] = useState(qFromUrl);

  useEffect(() => {
    setQ(qFromUrl);
  }, [qFromUrl]);

  const enabled = qFromUrl.length > 0;

  const query = useQuery({
    queryKey: ['search', qFromUrl],
    queryFn: () => search(qFromUrl),
    enabled,
  });

  const hasResults = useMemo(() => {
    if (!query.data) return false;
    return (query.data.clusters?.length || 0) > 0 || (query.data.topics?.length || 0) > 0;
  }, [query.data]);

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.title}>Search</h1>
          <form
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault();
              const next = q.trim();
              router.push(next ? `/search?q=${encodeURIComponent(next)}` : '/search');
            }}
          >
            <Input
              name="q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search stories, topics…"
              aria-label="Search stories and topics"
            />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </form>
        </header>

        {!enabled ? (
          <p className={styles.hint}>Look up stories or topics.</p>
        ) : query.isLoading ? (
          <p className={styles.hint}>Searching…</p>
        ) : query.isError ? (
          <p className={styles.error}>Search failed. Try again.</p>
        ) : !hasResults ? (
          <EmptySearch query={qFromUrl} />
        ) : (
          <div className={styles.results}>
            {query.data?.topics?.length ? (
              <section className={styles.section} aria-labelledby="topics-heading">
                <h2 id="topics-heading" className={styles.h2}>
                  Topics
                </h2>
                <div className={styles.topicGrid}>
                  {query.data.topics.map((t) => (
                    <Link
                      key={t.topic_id}
                      href={`${t.topic_type === 'category' ? '/category' : '/topic'}/${t.topic_id}`}
                      className={styles.topicCard}
                    >
                      <div className={styles.topicName}>{t.name}</div>
                      {t.description_short ? (
                        <div className={styles.topicDesc}>{t.description_short}</div>
                      ) : null}
                    </Link>
                  ))}
                </div>
              </section>
            ) : null}

            {query.data?.clusters?.length ? (
              <section className={styles.section} aria-labelledby="clusters-heading">
                <h2 id="clusters-heading" className={styles.h2}>
                  Stories
                </h2>
                <div className={styles.list}>
                  {query.data.clusters.map((c) => (
                    <ClusterCard key={c.cluster_id} cluster={c} />
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </div>
    </main>
  );
}
