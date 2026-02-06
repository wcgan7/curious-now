import { LoginPage } from '@/components/auth/LoginPage/LoginPage';
import { Suspense } from 'react';

export default function Login() {
  return (
    <Suspense fallback={<main style={{ padding: 'var(--s-8)' }}>Loading…</main>}>
      <LoginPage />
    </Suspense>
  );
}
