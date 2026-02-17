import Link from 'next/link';

import styles from './fallback.module.css';

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
            <Link href="/" className={styles.homeLink}>
              Go to home
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
