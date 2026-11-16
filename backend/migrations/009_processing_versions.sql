-- AGRISCAN 2.0 — migration 009: processing versions.
--
-- Adapted from PROMISE (pp. xviii, 21), where every screening result carries the version
-- of the rule set that produced it. AGRISCAN already records the model on every detection,
-- and the model row carries its own confidence and margin thresholds. What it did NOT record
-- is everything else that decides whether an image reaches the model and how its output is
-- read: the quality-gate limits, the palay gate, the detector implementation, and the
-- severity method. Change any of those in configuration and a historical detection could no
-- longer be reproduced. A processing version is an immutable snapshot of that configuration,
-- shared by every detection produced under it.

CREATE TABLE IF NOT EXISTS processing_versions (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  config_hash       CHAR(64) NOT NULL,
  pipeline_version  VARCHAR(32) NOT NULL,
  config_json       LONGTEXT NOT NULL,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_processing_versions_hash (config_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
-- @@
ALTER TABLE detections
  ADD COLUMN IF NOT EXISTS processing_version_id INT UNSIGNED NULL AFTER model_version_id
-- @@
ALTER TABLE detections
  ADD CONSTRAINT fk_detections_processing_version
  FOREIGN KEY (processing_version_id) REFERENCES processing_versions (id)
-- @@
DROP TRIGGER IF EXISTS trg_detections_immutable
-- @@
CREATE TRIGGER trg_detections_immutable
BEFORE UPDATE ON detections
FOR EACH ROW
BEGIN
  IF NOT (NEW.condition_id <=> OLD.condition_id) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'AGRISCAN rule 1: detections.condition_id is immutable. Write a verifications row instead.';
  END IF;
  IF NOT (NEW.confidence <=> OLD.confidence) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'AGRISCAN rule 1: detections.confidence is immutable.';
  END IF;
  IF NOT (NEW.model_version_id <=> OLD.model_version_id) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'AGRISCAN rule 1: detections.model_version_id is immutable.';
  END IF;
  IF NOT (NEW.image_id <=> OLD.image_id) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'AGRISCAN rule 1: detections.image_id is immutable.';
  END IF;
  -- A row written before this migration has no processing version and may be given one once.
  -- After that it is fixed.
  IF OLD.processing_version_id IS NOT NULL
     AND NOT (NEW.processing_version_id <=> OLD.processing_version_id) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'AGRISCAN rule 1: detections.processing_version_id is immutable once set.';
  END IF;
END
-- @@
DROP TRIGGER IF EXISTS trg_processing_versions_no_update
-- @@
CREATE TRIGGER trg_processing_versions_no_update
BEFORE UPDATE ON processing_versions
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'AGRISCAN: a processing version is an immutable snapshot. Create a new one.';
END
-- @@
DROP TRIGGER IF EXISTS trg_processing_versions_no_delete
-- @@
CREATE TRIGGER trg_processing_versions_no_delete
BEFORE DELETE ON processing_versions
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'AGRISCAN: processing versions are never deleted.';
END
