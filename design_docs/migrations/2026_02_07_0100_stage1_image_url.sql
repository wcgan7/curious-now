-- Migration: Add image_url column to items table
-- Purpose: Store featured/thumbnail image URLs extracted from RSS feeds

ALTER TABLE items ADD COLUMN IF NOT EXISTS image_url TEXT NULL;

-- Optional: Add an index if we expect to query by image availability
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_image_url_not_null
--   ON items (id) WHERE image_url IS NOT NULL;
