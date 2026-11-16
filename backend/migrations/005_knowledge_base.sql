-- AGRISCAN 2.0 — migration 005: agronomic knowledge base and recommendation caching
-- Idempotent.

-- One curated record per condition. Content is entered by the team from DA, PhilRice,
-- BPI and IRRI material. Nothing here is generated, and every row names its source.
CREATE TABLE IF NOT EXISTS knowledge_base (
  id                  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  condition_id        INT UNSIGNED NOT NULL,
  identification_cues TEXT NULL,
  cultural_measures   TEXT NULL,
  preventive_measures TEXT NULL,
  monitoring_guidance TEXT NULL,
  when_to_call        TEXT NULL,
  source_id           INT UNSIGNED NULL,
  content_status      ENUM('PLACEHOLDER','DRAFT','REVIEWED') NOT NULL DEFAULT 'PLACEHOLDER',
  reviewed_by         INT UNSIGNED NULL,
  reviewed_at         DATETIME NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_kb_condition (condition_id),
  KEY ix_kb_status (content_status),
  CONSTRAINT fk_kb_condition FOREIGN KEY (condition_id) REFERENCES conditions(id),
  CONSTRAINT fk_kb_source FOREIGN KEY (source_id) REFERENCES knowledge_sources(id),
  CONSTRAINT fk_kb_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cache key = condition + severity band + growth stage. An approved recommendation for
-- one combination is reused for the next identical case, so the feature works with no
-- internet and no second model call.
SET @c1 := (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recommendations'
              AND COLUMN_NAME = 'cache_key');
SET @d1 := IF(@c1 = 0,
  'ALTER TABLE recommendations ADD COLUMN cache_key VARCHAR(160) NULL AFTER status',
  'DO 0');
PREPARE s1 FROM @d1; EXECUTE s1; DEALLOCATE PREPARE s1;

SET @c2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recommendations'
              AND COLUMN_NAME = 'severity_band');
SET @d2 := IF(@c2 = 0,
  'ALTER TABLE recommendations ADD COLUMN severity_band VARCHAR(20) NULL AFTER cache_key',
  'DO 0');
PREPARE s2 FROM @d2; EXECUTE s2; DEALLOCATE PREPARE s2;

SET @c3 := (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recommendations'
              AND COLUMN_NAME = 'growth_stage');
SET @d3 := IF(@c3 = 0,
  'ALTER TABLE recommendations ADD COLUMN growth_stage VARCHAR(40) NULL AFTER severity_band',
  'DO 0');
PREPARE s3 FROM @d3; EXECUTE s3; DEALLOCATE PREPARE s3;

SET @c4 := (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recommendations'
              AND COLUMN_NAME = 'rejected_reason');
SET @d4 := IF(@c4 = 0,
  'ALTER TABLE recommendations ADD COLUMN rejected_reason TEXT NULL',
  'DO 0');
PREPARE s4 FROM @d4; EXECUTE s4; DEALLOCATE PREPARE s4;

SET @i1 := (SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recommendations'
              AND INDEX_NAME = 'ix_recommendations_cache');
SET @d5 := IF(@i1 = 0,
  'CREATE INDEX ix_recommendations_cache ON recommendations (cache_key, status)',
  'DO 0');
PREPARE s5 FROM @d5; EXECUTE s5; DEALLOCATE PREPARE s5;
