'use client';

import styles from './OfflineIndicator.module.css';
import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();
  if (isOnline) return null;

  return (
    <div className={styles.indicator} role="status" aria-live="polite">
      <span className={styles.dot} aria-hidden="true" />
      <span>You&apos;re offline. Saved stories may still be available.</span>
    </div>
  );
}

