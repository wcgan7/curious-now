import type { FeedStory } from "@/lib/types";

/** Deal one story from each publisher in turn, then go round again.
 *
 * The ranking deliberately carries no variety term: the old one multiplied a
 * story's stored score by how many same-source stories happened to be ranked
 * in the same batch, so two stories of identical merit took different
 * permanent scores. Spread is a property of a page, not of a story, so it is
 * applied here.
 *
 * Measured need: arXiv publishes in daily bulk, and the first page of the real
 * feed was 16 of 20 from one publisher before this.
 */
export function spreadSources(stories: FeedStory[]): FeedStory[] {
  const queues = new Map<string, FeedStory[]>();
  for (const story of stories) {
    // A story's publisher is the source of its principal item; stories with no
    // source at all queue together rather than each forming their own run.
    const key = story.sources[0]?.sourceName ?? "";
    const queue = queues.get(key);
    if (queue) {
      queue.push(story);
    } else {
      queues.set(key, [story]);
    }
  }

  // Insertion order is rank order, so the best-ranked publisher leads each
  // round and the page still opens with the story the ranking chose.
  const spread: FeedStory[] = [];
  while (spread.length < stories.length) {
    for (const queue of queues.values()) {
      const next = queue.shift();
      if (next) {
        spread.push(next);
      }
    }
  }
  return spread;
}

