-- AGRISCAN 2.0 — migration 004: separate job result from job error
-- A successful summary written into `error` makes every completed job look failed
-- to anyone reading the table. Results and errors are different things.

SET @col := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'jobs' AND COLUMN_NAME = 'result'
);
SET @ddl := IF(@col = 0,
  'ALTER TABLE jobs ADD COLUMN result JSON NULL AFTER payload',
  'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
