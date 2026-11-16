-- AGRISCAN p21 — migration 010: what a public deployment needs from the schema.
--
-- 1. users.password_changed_at
--    A token issued before a password change (or reset) must stop working. Every token
--    carries the password version it was issued under (this timestamp, to the
--    microsecond), and a token whose version no longer matches is refused.
--
-- 2. Index for the login rate limit
--    Failed sign-ins are already written to audit_log as action='login_failed' with the
--    attempted name in object_id. The limiter counts those rows over a time window, so
--    it needs (action, object_id, created_at) to stay fast as the log grows.
--
-- 3. jobs.image_id
--    The image list looked up each image's job with JSON_EXTRACT(payload, '$.image_id'),
--    which scans every job row. One drone flight at a 2 s interval is ~300 images, so
--    after a season that is a full scan of thousands of rows per image per page load.
--    A persistent generated column with an index turns it into a lookup. The payload
--    stays the source of truth; nothing writes this column directly.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_changed_at DATETIME(6) NULL AFTER password_hash;

CREATE INDEX IF NOT EXISTS ix_audit_action_object_time
  ON audit_log (action, object_id, created_at);

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS image_id BIGINT UNSIGNED
  AS (CAST(JSON_VALUE(payload, '$.image_id') AS UNSIGNED)) PERSISTENT;

CREATE INDEX IF NOT EXISTS ix_jobs_image ON jobs (image_id, id);
