'use client';

import styles from './ClusterCard.module.css';

export function ClusterCardImage({ src, alt }: { src: string; alt: string }) {
  return (
    <div className={styles.imageWrapper}>
      <img
        src={src}
        alt={alt}
        className={styles.image}
        loading="lazy"
        onError={(e) => {
          const wrapper = (e.target as HTMLElement).parentElement;
          if (wrapper) wrapper.style.display = 'none';
        }}
      />
    </div>
  );
}
