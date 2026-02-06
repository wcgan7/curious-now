import { VerifyPage } from '@/components/auth/VerifyPage/VerifyPage';
import { Suspense } from 'react';

export default function Verify() {
  return (
    <Suspense fallback={<main style={{ padding: 'var(--s-8)' }}>Loading…</main>}>
      <VerifyPage />
    </Suspense>
  );
}
