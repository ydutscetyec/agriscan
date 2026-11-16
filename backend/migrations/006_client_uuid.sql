-- AGRISCAN 2.0 — migration 006: client-generated capture id
-- The field client creates a UUID before the upload leaves the phone. Two things then
-- make a retry idempotent: this id, and the content hash from migration 001. The id
-- covers the case where a retry re-encodes the bytes slightly differently; the hash
-- covers the case where the same file is sent from two devices.

SET @col := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'images'
    AND COLUMN_NAME = 'client_uuid'
);
SET @ddl := IF(@col = 0,
  'ALTER TABLE images ADD COLUMN client_uuid CHAR(36) NULL AFTER uuid',
  'DO 0');
PREPARE s1 FROM @ddl; EXECUTE s1; DEALLOCATE PREPARE s1;

SET @idx := (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'images'
    AND INDEX_NAME = 'uq_images_client_uuid'
);
SET @ddl2 := IF(@idx = 0,
  'CREATE UNIQUE INDEX uq_images_client_uuid ON images (client_uuid)',
  'DO 0');
PREPARE s2 FROM @ddl2; EXECUTE s2; DEALLOCATE PREPARE s2;
