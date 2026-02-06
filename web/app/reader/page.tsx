import { ReaderPage } from '@/components/reader/ReaderPage/ReaderPage';
import { Suspense } from 'react';

export default function Reader() {
  return (
    <Suspense fallback={<main style={{ padding: 'var(--s-8)' }}>Loading…</main>}>
      <ReaderPage />
    </Suspense>
  );
}
