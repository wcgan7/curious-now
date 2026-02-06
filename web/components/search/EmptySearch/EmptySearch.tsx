import Link from 'next/link';
import { Search as SearchIcon } from 'lucide-react';

import styles from './EmptySearch.module.css';

export function EmptySearch({ query }: { query: string }) {
  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <SearchIcon className={styles.icon} />
      </div>
      <h3 className={styles.title}>No results for &quot;{query}&quot;</h3>
      <p className={styles.message}>
        Try a different keyword or check the spelling.
      </p>
      <div className={styles.suggestions}>
        <p className={styles.suggestionsLabel}>Try:</p>
        <div className={styles.suggestionsList}>
          {['CRISPR', 'battery', 'fusion', 'climate'].map((s) => (
            <Link
              key={s}
              href={`/search?q=${encodeURIComponent(s)}`}
              className={styles.suggestionChip}
            >
              {s}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

