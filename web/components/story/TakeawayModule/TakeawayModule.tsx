import styles from './TakeawayModule.module.css';

export function TakeawayModule({ takeaway }: { takeaway: string }) {
  return (
    <aside className={styles.module} aria-labelledby="takeaway-heading">
      <h2 id="takeaway-heading" className={styles.heading}>
        Takeaway
      </h2>
      <p className={styles.text}>{takeaway}</p>
    </aside>
  );
}

