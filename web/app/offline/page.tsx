import Link from 'next/link';

import styles from './page.module.css';

export const metadata = {
  title: 'Offline',
};

export default function OfflinePage() {
  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.title}>You&apos;re offline</h1>
        <p className={styles.p}>
          Check your connection and try again.
        </p>
        <div className={styles.row}>
          <Link href="/" className={styles.homeLink}>
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
