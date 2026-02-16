-- Pipeline scalability indexes
-- Target: support 1M items/month scaling to 100M items
-- All indexes use CONCURRENTLY to avoid blocking writes.

-- 1. Clustering: speed up NOT EXISTS check for unassigned items
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cluster_items_item_id_only
  ON cluster_items (item_id);

-- 2. Takeaway generation: find clusters needing takeaways
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clusters_needs_takeaway
  ON story_clusters (updated_at DESC)
  WHERE status IN ('active', 'pending') AND takeaway IS NULL AND distinct_source_count >= 1;

-- 3. Stage 3 enrichment: find clusters needing intuition or deep dive
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clusters_needs_stage3
  ON story_clusters (updated_at DESC)
  WHERE status IN ('active', 'pending') AND takeaway IS NOT NULL
    AND (summary_intuition IS NULL OR summary_deep_dive IS NULL);

-- 4. Deep dive: find clusters needing deep dive (used with EXISTS rewrite)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clusters_needs_deep_dive
  ON story_clusters (updated_at DESC)
  WHERE status IN ('active', 'pending') AND takeaway IS NOT NULL AND summary_deep_dive IS NULL;

-- 5. Topic tagging: reverse lookup on cluster_topics
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cluster_topics_cluster_id
  ON cluster_topics (cluster_id);

-- 6. Topic tagging: cluster_topics by cluster + score for ranking
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cluster_topics_cluster_score
  ON cluster_topics (cluster_id, score DESC);

-- 7. Paper hydration: find pending papers
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_paper_hydration_pending
  ON items (published_at DESC NULLS LAST, fetched_at DESC)
  WHERE content_type IN ('preprint', 'peer_reviewed')
    AND full_text_status = 'pending';

-- 8. Article hydration: find pending articles
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_article_hydration_pending2
  ON items (published_at DESC NULLS LAST, fetched_at DESC)
  WHERE content_type NOT IN ('preprint', 'peer_reviewed')
    AND full_text_status = 'pending';

-- 9. Image backfill: arXiv items missing images
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_arxiv_needs_image
  ON items (published_at DESC NULLS LAST)
  WHERE arxiv_id IS NOT NULL AND (image_url IS NULL OR btrim(image_url) = '');

-- 10. Image backfill: non-arXiv items missing images
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_landing_needs_image
  ON items (published_at DESC NULLS LAST)
  WHERE arxiv_id IS NULL
    AND (url IS NOT NULL OR canonical_url IS NOT NULL)
    AND (image_url IS NULL OR btrim(image_url) = '');

-- 11. Trending: cluster_items velocity lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cluster_items_added_at
  ON cluster_items (cluster_id, added_at DESC);

-- 12. Intuition only (no deep dive filter)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clusters_needs_intuition
  ON story_clusters (updated_at DESC)
  WHERE status IN ('active', 'pending') AND takeaway IS NOT NULL AND summary_intuition IS NULL;
