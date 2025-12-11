-- Add published_at column to leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS published_at timestamp with time zone;
