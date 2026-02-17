-- Add 'pending' status for clusters that haven't completed enrichment.
-- New clusters start as 'pending' and are promoted to 'active' once they
-- have a takeaway, intuition, and at least one topic tag.
-- Existing 'active' clusters are unaffected.
ALTER TYPE cluster_status ADD VALUE IF NOT EXISTS 'pending' BEFORE 'active';
