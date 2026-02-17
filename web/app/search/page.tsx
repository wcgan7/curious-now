import { SearchPage } from '@/components/search/SearchPage/SearchPage';
import { Suspense } from 'react';

export const metadata = { title: 'Search | Curious Now', description: 'Search across science stories, topics, and research.' };

export default function Search() {
  return (
    <Suspense fallback={<main style={{ padding: 'var(--s-8)' }}>Loading…</main>}>
      <SearchPage />
    </Suspense>
  );
}
