'use client';

import Link from 'next/link';

import styles from './fallback.module.css';
import { Button } from '@/components/ui/Button/Button';

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <section className={styles.card} aria-labelledby="error-heading">
          <p className={styles.kicker}>Curious Now</p>
          <h1 id="error-heading" className={styles.title}>
            Something went wrong
          </h1>
          <p className={styles.message}>
            {error.message || 'Please try again in a moment.'}
          </p>
          <div className={styles.actions}>
            <Button type="button" onClick={() => reset()}>
              Try again
            </Button>
            <Link href="/">
              <Button type="button" variant="secondary">
                Go to home
              </Button>
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
