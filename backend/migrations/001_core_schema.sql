-- AGRISCAN 2.0 — migration 001: core schema
-- Idempotent: safe to re-run. Engine InnoDB, utf8mb4.
-- is_demo marks synthetic rows; every metric/export query must exclude them by default.

CREATE TABLE IF NOT EXISTS users (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  role            ENUM('farmer','technician','researcher','admin') NOT NULL,
  name            VARCHAR(160) NOT NULL,
  barangay        VARCHAR(120) NULL,
  password_hash   VARCHAR(255) NOT NULL,
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_users_name (name),
  KEY ix_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS farms (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  owner_user_id   INT UNSIGNED NOT NULL,
  name            VARCHAR(160) NOT NULL,
  barangay        VARCHAR(120) NULL,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_farms_owner (owner_user_id),
  CONSTRAINT fk_farms_owner FOREIGN KEY (owner_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fields (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  farm_id         INT UNSIGNED NOT NULL,
  name            VARCHAR(160) NOT NULL,
  boundary_geojson JSON NULL,
  area_ha         DECIMAL(10,4) NULL,
  variety         VARCHAR(120) NULL,
  planting_date   DATE NULL,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_fields_farm (farm_id),
  CONSTRAINT fk_fields_farm FOREIGN KEY (farm_id) REFERENCES farms(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS missions (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id        INT UNSIGNED NOT NULL,
  operator_id     INT UNSIGNED NOT NULL,
  flown_at        DATETIME NULL,
  altitude_m      DECIMAL(6,2) NULL,
  pattern         VARCHAR(60) NULL,
  weather         VARCHAR(160) NULL,
  wind_ms         DECIMAL(5,2) NULL,
  aborted         BOOLEAN NOT NULL DEFAULT FALSE,
  abort_reason    VARCHAR(255) NULL,
  notes           TEXT NULL,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_missions_field (field_id),
  KEY ix_missions_flown_at (flown_at),
  CONSTRAINT fk_missions_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_missions_operator FOREIGN KEY (operator_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS conditions (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code            VARCHAR(80) NOT NULL,
  common_name     VARCHAR(160) NOT NULL,
  scientific_name VARCHAR(200) NULL,
  category        ENUM('healthy','fungal','bacterial','viral','pest','nutritional',
                       'abiotic','physical','weed','unknown') NOT NULL,
  tier            TINYINT UNSIGNED NULL,
  plant_part      VARCHAR(60) NULL,
  UNIQUE KEY uq_conditions_code (code),
  KEY ix_conditions_tier (tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS model_versions (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name              VARCHAR(160) NOT NULL,
  architecture      VARCHAR(120) NOT NULL,
  dataset_version   VARCHAR(120) NULL,
  trained_at        DATETIME NULL,
  metrics_json      JSON NULL,
  conf_threshold    DECIMAL(5,4) NULL,
  margin_threshold  DECIMAL(5,4) NULL,
  imaging_mode      ENUM('ground','aerial') NOT NULL DEFAULT 'ground',
  deployment_status ENUM('training','staged','production','retired') NOT NULL DEFAULT 'training',
  capability_status ENUM('DESIGNED','IMPLEMENTED','DATA_REQUIRED','HARDWARE_REQUIRED',
                         'EXPERIMENTAL','VALIDATED','NOT_VALIDATED','DEMO')
                    NOT NULL DEFAULT 'NOT_VALIDATED',
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_model_versions_name (name),
  KEY ix_model_versions_deploy (deployment_status, imaging_mode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS images (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  uuid          CHAR(36) NOT NULL,
  mission_id    INT UNSIGNED NULL,
  field_id      INT UNSIGNED NOT NULL,
  source        ENUM('drone','phone') NOT NULL,
  file_path     VARCHAR(512) NOT NULL,
  content_hash  CHAR(64) NOT NULL,
  lat           DECIMAL(10,7) NULL,
  lon           DECIMAL(10,7) NULL,
  gps_source    ENUM('exif','apm_log','manual','missing') NOT NULL DEFAULT 'missing',
  captured_at   DATETIME NULL,
  growth_stage  VARCHAR(40) NULL,
  quality_flag  ENUM('ok','blurred','dark','overexposed','unreadable') NULL,
  uploaded_by   INT UNSIGNED NOT NULL,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_images_content_hash (content_hash),
  UNIQUE KEY uq_images_uuid (uuid),
  KEY ix_images_field_captured (field_id, captured_at),
  KEY ix_images_mission (mission_id),
  CONSTRAINT fk_images_mission FOREIGN KEY (mission_id) REFERENCES missions(id),
  CONSTRAINT fk_images_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_images_uploader FOREIGN KEY (uploaded_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS detections (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  image_id         INT UNSIGNED NOT NULL,
  condition_id     INT UNSIGNED NULL,
  confidence       DECIMAL(5,4) NULL,
  bbox             JSON NULL,
  severity_value   DECIMAL(6,3) NULL,
  severity_method  VARCHAR(60) NULL,
  model_version_id INT UNSIGNED NOT NULL,
  status           ENUM('ai_detected','low_confidence','farmer_confirmed',
                        'technician_verified','rejected') NOT NULL DEFAULT 'ai_detected',
  is_demo          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_detections_image (image_id),
  KEY ix_detections_status (status),
  KEY ix_detections_condition (condition_id),
  KEY ix_detections_model (model_version_id),
  CONSTRAINT fk_detections_image FOREIGN KEY (image_id) REFERENCES images(id),
  CONSTRAINT fk_detections_condition FOREIGN KEY (condition_id) REFERENCES conditions(id),
  CONSTRAINT fk_detections_model FOREIGN KEY (model_version_id) REFERENCES model_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS verifications (
  id                      INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  detection_id            INT UNSIGNED NOT NULL,
  technician_id           INT UNSIGNED NOT NULL,
  decision                ENUM('correct','corrected','cannot_determine') NOT NULL,
  corrected_condition_id  INT UNSIGNED NULL,
  severity_score          TINYINT UNSIGNED NULL,
  notes                   TEXT NULL,
  is_demo                 BOOLEAN NOT NULL DEFAULT FALSE,
  verified_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_verifications_detection (detection_id),
  KEY ix_verifications_technician (technician_id),
  CONSTRAINT fk_verifications_detection FOREIGN KEY (detection_id) REFERENCES detections(id),
  CONSTRAINT fk_verifications_technician FOREIGN KEY (technician_id) REFERENCES users(id),
  CONSTRAINT fk_verifications_corrected FOREIGN KEY (corrected_condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS farmer_feedback (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  detection_id INT UNSIGNED NOT NULL,
  user_id      INT UNSIGNED NOT NULL,
  agrees       BOOLEAN NOT NULL,
  comment      TEXT NULL,
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_feedback_detection (detection_id),
  CONSTRAINT fk_feedback_detection FOREIGN KEY (detection_id) REFERENCES detections(id),
  CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_sources (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  title      VARCHAR(255) NOT NULL,
  publisher  VARCHAR(160) NOT NULL,
  year       SMALLINT UNSIGNED NULL,
  url        VARCHAR(512) NULL,
  locator    VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recommendations (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  detection_id INT UNSIGNED NOT NULL,
  text         TEXT NOT NULL,
  source_refs  JSON NULL,
  generated_by VARCHAR(120) NULL,
  approved_by  INT UNSIGNED NULL,
  approved_at  DATETIME NULL,
  status       ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_recommendations_detection (detection_id),
  KEY ix_recommendations_status (status),
  CONSTRAINT fk_recommendations_detection FOREIGN KEY (detection_id) REFERENCES detections(id),
  CONSTRAINT fk_recommendations_approver FOREIGN KEY (approved_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS annotations (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  image_id     INT UNSIGNED NOT NULL,
  annotator_id INT UNSIGNED NOT NULL,
  condition_id INT UNSIGNED NOT NULL,
  bbox         JSON NULL,
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_annotations_image (image_id),
  CONSTRAINT fk_annotations_image FOREIGN KEY (image_id) REFERENCES images(id),
  CONSTRAINT fk_annotations_annotator FOREIGN KEY (annotator_id) REFERENCES users(id),
  CONSTRAINT fk_annotations_condition FOREIGN KEY (condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_log (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NULL,
  action      VARCHAR(80) NOT NULL,
  object_type VARCHAR(80) NULL,
  object_id   VARCHAR(80) NULL,
  detail      JSON NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_audit_user (user_id),
  KEY ix_audit_created (created_at),
  KEY ix_audit_action (action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
