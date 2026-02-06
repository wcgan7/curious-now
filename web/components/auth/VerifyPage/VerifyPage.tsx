'use client';

import { useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';

import styles from './VerifyPage.module.css';
import { verifyMagicLink } from '@/lib/api/user';

export function VerifyPage() {
  const router = useRouter();
  const search = useSearchParams();
  const qc = useQueryClient();

  const token = search.get('token') || '';
  const redirectTo = search.get('redirect') || '/';

  const mutation = useMutation({
    mutationFn: async () => verifyMagicLink(token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['me'] });
      qc.invalidateQueries({ queryKey: ['prefs'] });
      router.replace(redirectTo);
    },
  });

  useEffect(() => {
    if (!token) return;
    if (mutation.isPending || mutation.isSuccess || mutation.isError) return;
    mutation.mutate();
  }, [token, mutation]);

  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.title}>Verifying…</h1>
        {!token ? (
          <p className={styles.p}>Missing token. Open the full magic link from your email.</p>
        ) : mutation.isError ? (
          <p className={styles.p}>
            This link is invalid or expired. Try logging in again.
          </p>
        ) : (
          <p className={styles.p}>One moment while we sign you in.</p>
        )}
      </div>
    </main>
  );
}

