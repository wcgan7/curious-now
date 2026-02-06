'use client';

import { useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import styles from './LogoutPage.module.css';
import { logout } from '@/lib/api/user';

export function LogoutPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      qc.setQueryData(['me'], null);
      qc.setQueryData(['prefs'], null);
      router.replace('/');
    },
    onError: () => {
      router.replace('/');
    },
  });

  useEffect(() => {
    if (!mutation.isIdle) return;
    mutation.mutate();
  }, [mutation]);

  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.title}>Logging out…</h1>
        <p className={styles.p}>One moment.</p>
      </div>
    </main>
  );
}

