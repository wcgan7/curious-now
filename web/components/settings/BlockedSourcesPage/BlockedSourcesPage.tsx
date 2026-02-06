'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';

import styles from './BlockedSourcesPage.module.css';
import { AuthGuard } from '@/components/auth/AuthGuard/AuthGuard';
import { Button } from '@/components/ui/Button/Button';
import { listSources } from '@/lib/api/sources';
import { usePrefs } from '@/lib/hooks/usePrefs';
import { unblockSource } from '@/lib/api/user';

export function BlockedSourcesPage() {
  return (
    <AuthGuard>
      <BlockedSourcesInner />
    </AuthGuard>
  );
}

function BlockedSourcesInner() {
  const qc = useQueryClient();
  const prefs = usePrefs();
  const sources = useQuery({ queryKey: ['sources'], queryFn: listSources });

  const blocked = useMemo(() => {
    const all = sources.data?.sources || [];
    const ids = new Set(prefs.data?.prefs.blocked_source_ids || []);
    return all
      .map((s) => s.source)
      .filter((s) => ids.has(s.source_id))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [sources.data, prefs.data]);

  const unblock = useMutation({
    mutationFn: async (sourceId: string) => unblockSource(sourceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prefs'] });
      qc.invalidateQueries({ queryKey: ['sources'] });
    },
  });

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <h1 className={styles.title}>Blocked sources</h1>
            <Link href="/settings" className={styles.back}>
              Back
            </Link>
          </div>
          <p className={styles.subtitle}>Sources you&apos;ve blocked across the app.</p>
        </header>

        {prefs.isLoading || sources.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : prefs.isError || sources.isError ? (
          <p className={styles.error}>Failed to load sources.</p>
        ) : blocked.length === 0 ? (
          <p className={styles.hint}>No blocked sources.</p>
        ) : (
          <ul className={styles.list}>
            {blocked.map((s) => (
              <li key={s.source_id} className={styles.item}>
                <div className={styles.mainCol}>
                  <div className={styles.name}>{s.name}</div>
                  <div className={styles.meta}>
                    <span>{s.source_type}</span>
                    {s.reliability_tier ? (
                      <>
                        <span aria-hidden="true">&middot;</span>
                        <span>{s.reliability_tier}</span>
                      </>
                    ) : null}
                  </div>
                </div>
                <Button
                  variant="tertiary"
                  size="sm"
                  leftIcon={<Trash2 size={16} />}
                  isLoading={unblock.isPending && unblock.variables === s.source_id}
                  onClick={() => unblock.mutate(s.source_id)}
                >
                  Unblock
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
