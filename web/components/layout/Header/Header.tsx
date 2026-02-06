'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';

import styles from './Header.module.css';
import { useMe } from '@/lib/hooks/useMe';

export function Header() {
  const pathname = usePathname();
  const me = useMe();
  const authed = Boolean(me.data?.user);
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand}>
          Curious Now
        </Link>

        <nav className={styles.nav} aria-label="Primary">
          <Link href="/" className={clsx(styles.navLink, isActive('/') && styles.active)}>
            Latest
          </Link>
          <Link
            href="/trending"
            className={clsx(styles.navLink, isActive('/trending') && styles.active)}
          >
            Trending
          </Link>
          <Link
            href="/for-you"
            className={clsx(styles.navLink, isActive('/for-you') && styles.active)}
          >
            For you
          </Link>
          <Link
            href="/search"
            className={clsx(styles.navLink, isActive('/search') && styles.active)}
          >
            Search
          </Link>
        </nav>

        <div className={styles.right}>
          <Link href="/saved" className={styles.iconLink}>
            Saved
          </Link>
          <Link href="/settings" className={styles.iconLink}>
            Settings
          </Link>
          {authed ? (
            <Link href="/auth/logout" className={styles.iconLink}>
              Logout
            </Link>
          ) : (
            <Link href="/auth/login" className={styles.iconLink}>
              Login
            </Link>
          )}
        </div>
      </div>

      <nav className={styles.mobileNav} aria-label="Primary mobile">
        <Link href="/" className={clsx(styles.mobileLink, isActive('/') && styles.activeMobile)}>
          Latest
        </Link>
        <Link
          href="/trending"
          className={clsx(styles.mobileLink, isActive('/trending') && styles.activeMobile)}
        >
          Trending
        </Link>
        <Link
          href="/for-you"
          className={clsx(styles.mobileLink, isActive('/for-you') && styles.activeMobile)}
        >
          For you
        </Link>
        <Link
          href="/saved"
          className={clsx(styles.mobileLink, isActive('/saved') && styles.activeMobile)}
        >
          Saved
        </Link>
      </nav>
    </header>
  );
}
