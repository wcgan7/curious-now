-- Backfill: set pending status for existing non-paper items missing full text
UPDATE items
SET full_text_status = 'pending'
WHERE content_type NOT IN ('preprint', 'peer_reviewed')
  AND (full_text IS NULL OR btrim(full_text) = '')
  AND full_text_status IS NULL;

-- Index for efficient article hydration queries
CREATE INDEX IF NOT EXISTS idx_items_article_text_pending
  ON items (content_type, full_text_status, published_at DESC NULLS LAST)
  WHERE content_type NOT IN ('preprint', 'peer_reviewed')
    AND full_text_status = 'pending';
