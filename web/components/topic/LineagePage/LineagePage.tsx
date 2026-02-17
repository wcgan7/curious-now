import Link from 'next/link';

import type { TopicLineageResponse } from '@/types/api';
import styles from './LineagePage.module.css';

export function LineagePage({ lineage }: { lineage: TopicLineageResponse }) {
  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.topRow}>
            <h1 className={styles.title}>Lineage</h1>
            <Link href={`/topic/${lineage.topic_id}`} className={styles.back}>
              Back
            </Link>
          </div>
          <p className={styles.subtitle}>
            A simple nodes/edges view of related papers, models, datasets, and methods.
          </p>
        </header>

        <section className={styles.section} aria-labelledby="nodes-heading">
          <h2 id="nodes-heading" className={styles.h2}>
            Nodes
          </h2>
          <ul className={styles.list}>
            {lineage.nodes.map((n) => (
              <li key={n.node_id} className={styles.item}>
                <div className={styles.nodeTitle}>
                  {n.external_url ? (
                    <a className={styles.nodeLink} href={n.external_url} target="_blank" rel="noopener noreferrer">
                      {n.title}
                    </a>
                  ) : (
                    n.title
                  )}
                </div>
                <div className={styles.meta}>
                  <span>{n.node_type}</span>
                  {n.published_at ? (
                    <>
                      <span aria-hidden="true">&middot;</span>
                      <time dateTime={n.published_at}>
                        {new Date(n.published_at).toLocaleDateString()}
                      </time>
                    </>
                  ) : null}
                </div>
                <div className={styles.mono}>{n.node_id}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section} aria-labelledby="edges-heading">
          <h2 id="edges-heading" className={styles.h2}>
            Edges
          </h2>
          <ul className={styles.list}>
            {lineage.edges.map((e) => (
              <li key={`${e.from}-${e.to}-${e.relation_type}`} className={styles.item}>
                <div className={styles.edgeRow}>
                  <span className={styles.mono}>{e.from}</span>
                  <span className={styles.edgeRel}>{e.relation_type}</span>
                  <span className={styles.mono}>{e.to}</span>
                </div>
                {e.notes_short ? <div className={styles.notes}>{e.notes_short}</div> : null}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}

