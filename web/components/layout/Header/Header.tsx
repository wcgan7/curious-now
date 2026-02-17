'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';

import styles from './Header.module.css';

export function Header() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);
  const categoriesActive = isActive('/categories') || isActive('/category');

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
            In Focus
          </Link>
          <Link href="/categories" className={clsx(styles.navLink, categoriesActive && styles.active)}>
            Categories
          </Link>
          <Link
            href="/search"
            className={clsx(styles.navLink, isActive('/search') && styles.active)}
          >
            Search
          </Link>
        </nav>
      </div>

      <nav className={styles.mobileNav} aria-label="Primary mobile">
        <Link href="/" className={clsx(styles.mobileLink, isActive('/') && styles.activeMobile)}>
          Latest
        </Link>
        <Link
          href="/trending"
          className={clsx(styles.mobileLink, isActive('/trending') && styles.activeMobile)}
        >
          In Focus
        </Link>
        <Link
          href="/categories"
          className={clsx(styles.mobileLink, categoriesActive && styles.activeMobile)}
        >
          Categories
        </Link>
        <Link
          href="/search"
          className={clsx(styles.mobileLink, isActive('/search') && styles.activeMobile)}
        >
          Search
        </Link>
      </nav>
    </header>
  );
}
