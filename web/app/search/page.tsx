import { SearchPage } from '@/components/search/SearchPage/SearchPage';
import { Suspense } from 'react';

export default function Search() {
  return (
    <Suspense fallback={<main style={{ padding: 'var(--s-8)' }}>Loading…</main>}>
      <SearchPage />
    </Suspense>
  );
}
