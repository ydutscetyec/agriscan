-- AGRISCAN 2.0 — migration 003: inference job queue and aerial taxonomy flag
-- Idempotent.

CREATE TABLE IF NOT EXISTS jobs (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  type          VARCHAR(40) NOT NULL DEFAULT 'inference',
  status        ENUM('QUEUED','RUNNING','COMPLETED','FAILED','RETRYING')
                NOT NULL DEFAULT 'QUEUED',
  priority      TINYINT NOT NULL DEFAULT 0,
  payload       JSON NULL,
  claimed_by    VARCHAR(64) NULL,
  attempts      TINYINT UNSIGNED NOT NULL DEFAULT 0,
  error         TEXT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at    DATETIME NULL,
  completed_at  DATETIME NULL,
  KEY ix_jobs_status_priority (status, priority, id),
  KEY ix_jobs_claim (claimed_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rule 6: aerial imagery may only produce zone-level labels. Which codes are
-- zone-level is TAXONOMY, so it lives in the database, not in worker code.
-- MariaDB has no ADD COLUMN IF NOT EXISTS in all versions, so guard with a check.
SET @col := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'conditions'
    AND COLUMN_NAME = 'aerial_allowed'
);
SET @ddl := IF(@col = 0,
  'ALTER TABLE conditions ADD COLUMN aerial_allowed BOOLEAN NOT NULL DEFAULT FALSE',
  'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Zone-level placeholder used when an aerial frame shows something abnormal that
-- cannot be named from that altitude. It is NOT a diagnosis.
INSERT INTO conditions (code, common_name, scientific_name, category, tier, aerial_allowed)
SELECT 'anomaly_zone', 'Anomalous zone (aerial, unnamed)', NULL, 'unknown', 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM conditions WHERE code = 'anomaly_zone');

-- Conditions genuinely resolvable at 15-30 m with an RGB phone camera.
UPDATE conditions SET aerial_allowed = TRUE
  WHERE code IN ('healthy', 'lodging', 'flooding', 'anomaly_zone', 'unknown');

-- Everything lesion-level stays ground-only. Explicit, so a later taxonomy edit
-- cannot silently widen what the drone is allowed to claim.
UPDATE conditions SET aerial_allowed = FALSE
  WHERE code IN ('bacterial_leaf_blight', 'rice_blast', 'brown_spot',
                 'hopperburn', 'nitrogen_deficiency');
