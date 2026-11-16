-- AGRISCAN 2.0 — migration 008: remote capture from the drone-mounted phone
--
-- The phone on the drone opens the /capture page, registers as a device, and polls for
-- a capture session. A technician arms a session from the dashboard while the aircraft
-- is on the ground and in Wi-Fi range. Capture then runs on the phone autonomously,
-- with a hard duration limit, and uploads after landing.
--
-- Photos taken by a web page carry no EXIF GPS, so position comes from the browser
-- Geolocation API at the moment of capture. That source is recorded as 'device', with
-- its reported accuracy, distinct from EXIF.
-- Idempotent.

CREATE TABLE IF NOT EXISTS capture_devices (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  registered_by INT UNSIGNED NOT NULL,
  user_agent    VARCHAR(255) NULL,
  last_seen_at  DATETIME NULL,
  battery_pct   TINYINT UNSIGNED NULL,
  charging      BOOLEAN NULL,
  gps_accuracy_m DECIMAL(8,2) NULL,
  camera_ready  BOOLEAN NOT NULL DEFAULT FALSE,
  capabilities  JSON NULL,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_devices_seen (last_seen_at),
  CONSTRAINT fk_device_user FOREIGN KEY (registered_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- max_duration_s is mandatory: if the phone loses contact at altitude it must still
-- stop on its own, not capture until the battery dies.
CREATE TABLE IF NOT EXISTS capture_sessions (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  device_id       INT UNSIGNED NOT NULL,
  field_id        INT UNSIGNED NOT NULL,
  mission_id      INT UNSIGNED NULL,
  interval_s      DECIMAL(5,2) NOT NULL,
  max_duration_s  SMALLINT UNSIGNED NOT NULL,
  max_shots       SMALLINT UNSIGNED NULL,
  status          ENUM('armed','running','stopped','completed','expired','failed')
                  NOT NULL DEFAULT 'armed',
  created_by      INT UNSIGNED NOT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at      DATETIME NULL,
  ended_at        DATETIME NULL,
  end_reason      VARCHAR(160) NULL,
  shots_reported  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_session_device (device_id, status),
  CONSTRAINT fk_session_device FOREIGN KEY (device_id) REFERENCES capture_devices(id),
  CONSTRAINT fk_session_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_session_mission FOREIGN KEY (mission_id) REFERENCES missions(id),
  CONSTRAINT fk_session_user FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- images: link to the session, and store device-reported position accuracy.
SET @c1 := (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'images'
              AND COLUMN_NAME = 'capture_session_id');
SET @d1 := IF(@c1 = 0,
  'ALTER TABLE images
     ADD COLUMN capture_session_id INT UNSIGNED NULL AFTER mission_id,
     ADD COLUMN gps_accuracy_m DECIMAL(8,2) NULL AFTER lon,
     ADD COLUMN gps_altitude_m DECIMAL(8,2) NULL AFTER gps_accuracy_m,
     ADD CONSTRAINT fk_images_session FOREIGN KEY (capture_session_id)
       REFERENCES capture_sessions(id)',
  'DO 0');
PREPARE s1 FROM @d1; EXECUTE s1; DEALLOCATE PREPARE s1;

-- 'device' = browser Geolocation API at capture time. Kept distinct from 'exif' so the
-- paper can report which images were positioned by which method.
ALTER TABLE images MODIFY COLUMN gps_source
  ENUM('exif','apm_log','manual','device','missing') NOT NULL DEFAULT 'missing';
