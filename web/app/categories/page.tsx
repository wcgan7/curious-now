import Link from 'next/link';

import { getTopics } from '@/lib/api/topics';

import styles from './page.module.css';

export default async function CategoriesPage() {
  const topics = await getTopics();
  const categories = topics.topics.filter((topic) => topic.topic_type === 'category');
  const subtopicsByCategory = new Map<string, number>();

  for (const topic of topics.topics) {
    if (topic.topic_type !== 'subtopic' || !topic.parent_topic_id) continue;
    subtopicsByCategory.set(
      topic.parent_topic_id,
      (subtopicsByCategory.get(topic.parent_topic_id) || 0) + 1
    );
  }

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <p className={styles.kicker}>Browse</p>
          <h1 className={styles.title}>Top categories</h1>
          <p className={styles.subtitle}>Choose a category to read only stories in that area.</p>
        </header>

        {categories.length ? (
          <section className={styles.grid} aria-label="Category list">
            {categories.map((category) => {
              const subtopicCount = subtopicsByCategory.get(category.topic_id) || 0;
              return (
                <Link
                  key={category.topic_id}
                  className={styles.card}
                  href={`/category/${category.topic_id}`}
                >
                  <div className={styles.cardTitle}>{category.name}</div>
                  {category.description_short ? (
                    <p className={styles.cardDesc}>{category.description_short}</p>
                  ) : null}
                  <p className={styles.cardMeta}>
                    {subtopicCount} subtopic{subtopicCount === 1 ? '' : 's'}
                  </p>
                </Link>
              );
            })}
          </section>
        ) : (
          <p className={styles.empty}>No categories available yet.</p>
        )}
      </div>
    </main>
  );
}
