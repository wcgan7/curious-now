import Link from 'next/link';

import { getTopics } from '@/lib/api/topics';

import styles from './page.module.css';

export const metadata = { title: 'Categories | Curious Now', description: 'Browse science stories by category and topic.' };

const SEEDED_CATEGORY_ORDER = [
  'Artificial Intelligence',
  'Computing',
  'Life Sciences',
  'Health & Medicine',
  'Physics',
  'Chemistry',
  'Earth & Environment',
  'Climate',
  'Space',
  'Energy',
  'Materials & Engineering',
  'Math & Economics',
  'Mind & Behavior',
] as const;
const SEEDED_CATEGORY_RANK: ReadonlyMap<string, number> = new Map(
  SEEDED_CATEGORY_ORDER.map((name, idx) => [name, idx] as const)
);

export default async function CategoriesPage() {
  const topics = await getTopics();
  const subtopicsByCategory = new Map<string, number>();
  const topicList = topics?.topics ?? [];

  for (const topic of topicList) {
    if (topic.topic_type !== 'subtopic' || !topic.parent_topic_id) continue;
    subtopicsByCategory.set(
      topic.parent_topic_id,
      (subtopicsByCategory.get(topic.parent_topic_id) || 0) + 1
    );
  }
  const categories = topicList
    .filter(
      (topic) => topic.topic_type === 'category' && (subtopicsByCategory.get(topic.topic_id) || 0) > 0
    )
    .sort((a, b) => {
      const aIdx = SEEDED_CATEGORY_RANK.get(a.name);
      const bIdx = SEEDED_CATEGORY_RANK.get(b.name);
      if (aIdx != null || bIdx != null) {
        if (aIdx == null) return 1;
        if (bIdx == null) return -1;
        return aIdx - bIdx;
      }
      return a.name.localeCompare(b.name);
    });

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <p className={styles.kicker}>Browse</p>
          <h1 className={styles.title}>Top categories</h1>
          <p className={styles.subtitle}>Browse stories by category.</p>
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
