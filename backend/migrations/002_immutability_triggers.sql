-- AGRISCAN 2.0 — migration 002: integrity triggers
-- Rule 1: a detection row is immutable once written. Corrections live in verifications.
-- status IS allowed to change (ai_detected -> technician_verified etc.); the diagnosis is not.
-- <=> is the NULL-safe equality operator, so NULL -> value is caught too.

DROP TRIGGER IF EXISTS trg_detections_immutable;
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
END;
-- @@
DROP TRIGGER IF EXISTS trg_audit_log_no_update;
-- @@
CREATE TRIGGER trg_audit_log_no_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'AGRISCAN: audit_log is append-only.';
END;
-- @@
DROP TRIGGER IF EXISTS trg_audit_log_no_delete;
-- @@
CREATE TRIGGER trg_audit_log_no_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'AGRISCAN: audit_log is append-only.';
END;
