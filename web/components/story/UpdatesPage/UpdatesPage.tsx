import Link from 'next/link';

import type { ClusterUpdatesResponse } from '@/types/api';

import styles from './UpdatesPage.module.css';

export function UpdatesPage({
  clusterId,
  updates,
}: {
  clusterId: string;
  updates: ClusterUpdatesResponse;
}) {
  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <div className={styles.top}>
          <h1 className={styles.title}>Updates</h1>
          <Link href={`/story/${clusterId}`} className={styles.back}>
            Back to story
          </Link>
        </div>

        <ul className={styles.list}>
          {updates.updates.map((u, idx) => (
            <li key={`${u.created_at}-${u.change_type}-${idx}`} className={styles.item}>
              <div className={styles.meta}>
                <time dateTime={u.created_at}>
                  {new Date(u.created_at).toLocaleString()}
                </time>
                <span aria-hidden="true">&middot;</span>
                <span>{u.change_type}</span>
              </div>
              <p className={styles.summary}>{u.summary}</p>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
