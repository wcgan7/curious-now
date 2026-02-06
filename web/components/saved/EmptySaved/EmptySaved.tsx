import Link from 'next/link';
import { Bookmark } from 'lucide-react';

import styles from './EmptySaved.module.css';
import { Button } from '@/components/ui/Button/Button';

export function EmptySaved() {
  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <Bookmark className={styles.icon} />
      </div>
      <h3 className={styles.title}>No saved stories yet</h3>
      <p className={styles.message}>
        Save a story to read it later. Saved stories can be available offline too.
      </p>
      <Link href="/">
        <Button variant="primary">Browse stories</Button>
      </Link>
    </div>
  );
}

