import Link from 'next/link';

import styles from './fallback.module.css';
import { Button } from '@/components/ui/Button/Button';

export default function NotFound() {
  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <section className={styles.card} aria-labelledby="not-found-heading">
          <p className={styles.kicker}>Curious Now</p>
          <h1 id="not-found-heading" className={styles.title}>
            Not found
          </h1>
          <p className={styles.message}>
            This page doesn&apos;t exist or may have moved.
          </p>
          <div className={styles.actions}>
            <Link href="/">
              <Button type="button">Go to home</Button>
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
