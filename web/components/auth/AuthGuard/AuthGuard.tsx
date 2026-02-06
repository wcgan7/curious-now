'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';

import { useMe } from '@/lib/hooks/useMe';
import { Button } from '@/components/ui/Button/Button';
import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';

export function AuthGuard({
  children,
  allowOffline = false,
}: {
  children: React.ReactNode;
  allowOffline?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useMe();
  const { isOnline } = useNetworkStatus();

  const loginHref = `/auth/login?redirect=${encodeURIComponent(pathname || '/')}`;
  const bypassAuth = !isOnline && allowOffline;

  useEffect(() => {
    if (bypassAuth) return;
    if (me.isLoading) return;
    const authed = Boolean(me.data?.user);
    if (!authed) {
      router.replace(loginHref);
    }
  }, [bypassAuth, me.isLoading, me.data, router, loginHref]);

  if (bypassAuth) {
    return <>{children}</>;
  }

  if (me.isLoading) {
    return (
      <main style={{ padding: 'var(--s-8)', maxWidth: 900, margin: '0 auto' }}>
        <p>Loading…</p>
      </main>
    );
  }

  if (!me.data?.user) {
    return (
      <main style={{ padding: 'var(--s-8)', maxWidth: 900, margin: '0 auto' }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>Login required</h1>
        <p style={{ color: 'var(--text-2)', lineHeight: 1.6 }}>
          Redirecting to login. If nothing happens, use the button below.
        </p>
        <Link href={loginHref}>
          <Button variant="primary">Go to login</Button>
        </Link>
      </main>
    );
  }

  return <>{children}</>;
}
