'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';

import styles from './FollowedTopicsPage.module.css';
import { AuthGuard } from '@/components/auth/AuthGuard/AuthGuard';
import { Button } from '@/components/ui/Button/Button';
import { listTopics } from '@/lib/api/topicsPublic';
import { usePrefs } from '@/lib/hooks/usePrefs';
import { unfollowTopic } from '@/lib/api/user';

export function FollowedTopicsPage() {
  return (
    <AuthGuard>
      <FollowedTopicsInner />
    </AuthGuard>
  );
}

function FollowedTopicsInner() {
  const qc = useQueryClient();
  const prefs = usePrefs();
  const topics = useQuery({ queryKey: ['topics'], queryFn: listTopics });

  const followed = useMemo(() => {
    const all = topics.data?.topics || [];
    const ids = new Set(prefs.data?.prefs.followed_topic_ids || []);
    return all.filter((t) => ids.has(t.topic_id));
  }, [topics.data, prefs.data]);

  const unfollow = useMutation({
    mutationFn: async (topicId: string) => unfollowTopic(topicId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prefs'] });
      qc.invalidateQueries({ queryKey: ['topics'] });
    },
  });

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <h1 className={styles.title}>Followed topics</h1>
            <Link href="/settings" className={styles.back}>
              Back
            </Link>
          </div>
          <p className={styles.subtitle}>Topics you&apos;ve chosen to follow.</p>
        </header>

        {prefs.isLoading || topics.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : prefs.isError || topics.isError ? (
          <p className={styles.error}>Failed to load topics.</p>
        ) : followed.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.hint}>You&apos;re not following any topics yet.</p>
            <Link href="/search" className={styles.cta}>
              Find topics in search
            </Link>
          </div>
        ) : (
          <ul className={styles.list}>
            {followed.map((t) => (
              <li key={t.topic_id} className={styles.item}>
                <div className={styles.mainCol}>
                  <Link href={`/topic/${t.topic_id}`} className={styles.name}>
                    {t.name}
                  </Link>
                  {t.description_short ? (
                    <div className={styles.desc}>{t.description_short}</div>
                  ) : null}
                </div>
                <Button
                  variant="tertiary"
                  size="sm"
                  leftIcon={<Trash2 size={16} />}
                  isLoading={unfollow.isPending && unfollow.variables === t.topic_id}
                  onClick={() => unfollow.mutate(t.topic_id)}
                >
                  Unfollow
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
