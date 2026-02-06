import Link from 'next/link';

import styles from './page.module.css';
import { Button } from '@/components/ui/Button/Button';

export const metadata = {
  title: 'Offline',
};

export default function OfflinePage() {
  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <h1 className={styles.title}>You&apos;re offline</h1>
        <p className={styles.p}>
          Check your connection. If you&apos;ve downloaded stories for offline, you can still read them from Saved.
        </p>
        <div className={styles.row}>
          <Link href="/saved">
            <Button variant="primary">Saved</Button>
          </Link>
          <Link href="/">
            <Button variant="secondary">Home</Button>
          </Link>
        </div>
      </div>
    </main>
  );
}

