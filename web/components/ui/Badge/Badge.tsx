import clsx from 'clsx';

import styles from './Badge.module.css';

export function Badge({
  children,
  variant = 'default',
}: {
  children: React.ReactNode;
  variant?: 'default' | 'warning' | 'success' | 'info';
}) {
  return <span className={clsx(styles.badge, styles[variant])}>{children}</span>;
}

export function ContentTypeBadge({ type }: { type: string }) {
  return <span className={styles.contentType}>{type.replace(/_/g, ' ')}</span>;
}

