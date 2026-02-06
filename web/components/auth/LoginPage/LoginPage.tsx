'use client';

import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';

import styles from './LoginPage.module.css';
import { Input } from '@/components/ui/Input/Input';
import { Button } from '@/components/ui/Button/Button';
import { startMagicLink } from '@/lib/api/user';

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function LoginPage() {
  const search = useSearchParams();
  const redirectTo = search.get('redirect') || '/';

  const [email, setEmail] = useState('');

  const mutation = useMutation({
    mutationFn: async () => startMagicLink(email.trim()),
  });

  const emailError = useMemo(() => {
    if (!email) return undefined;
    if (!isValidEmail(email)) return 'Enter a valid email address';
    return undefined;
  }, [email]);

  const disabled = mutation.isPending || !email.trim() || !!emailError;

  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.title}>Log in</h1>
        <p className={styles.subtitle}>
          We&apos;ll email you a magic link. After verifying, you&apos;ll be redirected to{' '}
          <code className={styles.code}>{redirectTo}</code>.
        </p>

        {mutation.isSuccess ? (
          <div className={styles.sent}>
            <h2 className={styles.h2}>Check your email</h2>
            <p className={styles.p}>
              If an account exists for <strong>{email.trim()}</strong>, you&apos;ll receive a link
              shortly.
            </p>
            <p className={styles.pSmall}>
              Local dev: the backend may log the link token to the server console.
            </p>
            <Button variant="secondary" onClick={() => mutation.reset()}>
              Send another link
            </Button>
          </div>
        ) : (
          <form
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault();
              if (disabled) return;
              mutation.mutate();
            }}
          >
            <Input
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={mutation.isError ? 'Unable to send magic link. Try again.' : emailError}
              placeholder="you@example.com"
            />

            <Button type="submit" isLoading={mutation.isPending} disabled={disabled}>
              Send magic link
            </Button>
          </form>
        )}
      </div>
    </main>
  );
}

