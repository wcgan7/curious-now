import Link from 'next/link';
import clsx from 'clsx';

import styles from './Card.module.css';

type CardAs = 'div' | 'article';

export function Card({
  as = 'div',
  href,
  className,
  children,
}: {
  as?: CardAs;
  href?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const Comp: React.ElementType = as;
  const content = (
    <Comp className={clsx(styles.card, className)}>{children}</Comp>
  );
  if (href) {
    return (
      <Link href={href} className={styles.linkWrapper}>
        {content}
      </Link>
    );
  }
  return content;
}

Card.Content = function CardContent({ children }: { children: React.ReactNode }) {
  return <div className={styles.content}>{children}</div>;
};

Card.Title = function CardTitle({ children }: { children: React.ReactNode }) {
  return <h2 className={styles.title}>{children}</h2>;
};

Card.Meta = function CardMeta({ children }: { children: React.ReactNode }) {
  return <div className={styles.meta}>{children}</div>;
};

