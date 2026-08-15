-- ============================================================
-- MIGRATION: ENABLE ROW LEVEL SECURITY (RLS)
-- Run this in your Supabase SQL editor to apply RLS to existing tables
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- Drop policy if it exists (for idempotency in reruns)
DROP POLICY IF EXISTS "User isolation" ON users;
CREATE POLICY "User isolation" ON users FOR ALL USING (telegram_id = current_setting('request.jwt.claim.sub', true));

ALTER TABLE staged_files ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "User isolation" ON staged_files;
CREATE POLICY "User isolation" ON staged_files FOR ALL USING (telegram_id = current_setting('request.jwt.claim.sub', true));

ALTER TABLE commit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "User isolation" ON commit_log;
CREATE POLICY "User isolation" ON commit_log FOR ALL USING (telegram_id = current_setting('request.jwt.claim.sub', true));
