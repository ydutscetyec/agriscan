-- AGRISCAN 2.0 — migration 007: Track B storage
--
-- These tables exist so the schema is ready when a sensor, a data source or a season of
-- history arrives. They are EMPTY by design. Nothing in the dashboard reads them, and
-- no navigation entry points at them: a page fed by a simulator invites a question that
-- has no honest answer.
--
-- Every table carries is_demo, so simulated rows can never be counted as observations.
-- Idempotent.

-- ------------------------------------------------------------------ drone / flight

CREATE TABLE IF NOT EXISTS mission_waypoints (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mission_id   INT UNSIGNED NOT NULL,
  sequence     SMALLINT UNSIGNED NOT NULL,
  lat          DECIMAL(10,7) NOT NULL,
  lon          DECIMAL(10,7) NOT NULL,
  altitude_m   DECIMAL(6,2) NULL,
  action       VARCHAR(40) NULL,
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_waypoint_seq (mission_id, sequence),
  CONSTRAINT fk_wp_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS drone_telemetry (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mission_id     INT UNSIGNED NOT NULL,
  recorded_at    DATETIME(3) NOT NULL,
  lat            DECIMAL(10,7) NULL,
  lon            DECIMAL(10,7) NULL,
  altitude_m     DECIMAL(7,2) NULL,
  ground_speed_ms DECIMAL(6,2) NULL,
  heading_deg    DECIMAL(5,1) NULL,
  battery_v      DECIMAL(5,2) NULL,
  battery_pct    TINYINT UNSIGNED NULL,
  satellites     TINYINT UNSIGNED NULL,
  flight_mode    VARCHAR(40) NULL,
  source         VARCHAR(40) NOT NULL DEFAULT 'NullProvider',
  is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_telemetry_mission (mission_id, recorded_at),
  CONSTRAINT fk_tel_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- fix_type is an ENUM so a plain GPS fix can never be recorded as RTK by a typo.
CREATE TABLE IF NOT EXISTS rtk_observations (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mission_id        INT UNSIGNED NULL,
  image_id          INT UNSIGNED NULL,
  recorded_at       DATETIME(3) NOT NULL,
  lat               DECIMAL(12,9) NOT NULL,
  lon               DECIMAL(12,9) NOT NULL,
  altitude_m        DECIMAL(8,3) NULL,
  fix_type          ENUM('NO_FIX','GPS','DGPS','RTK_FLOAT','RTK_FIXED') NOT NULL,
  horizontal_accuracy_m DECIMAL(6,3) NULL,
  vertical_accuracy_m   DECIMAL(6,3) NULL,
  correction_source VARCHAR(80) NULL,
  satellites        TINYINT UNSIGNED NULL,
  source            VARCHAR(40) NOT NULL DEFAULT 'NullProvider',
  is_demo           BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_rtk_mission (mission_id, recorded_at),
  KEY ix_rtk_fix (fix_type),
  CONSTRAINT fk_rtk_mission FOREIGN KEY (mission_id) REFERENCES missions(id),
  CONSTRAINT fk_rtk_image FOREIGN KEY (image_id) REFERENCES images(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------ remote sensing bands

CREATE TABLE IF NOT EXISTS image_bands (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  image_id        INT UNSIGNED NOT NULL,
  band            VARCHAR(20) NOT NULL,
  centre_wavelength_nm SMALLINT UNSIGNED NULL,
  bandwidth_nm    SMALLINT UNSIGNED NULL,
  file_path       VARCHAR(512) NULL,
  sensor_model    VARCHAR(120) NULL,
  calibrated      BOOLEAN NOT NULL DEFAULT FALSE,
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_image_band (image_id, band),
  CONSTRAINT fk_band_image FOREIGN KEY (image_id) REFERENCES images(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------- soil

CREATE TABLE IF NOT EXISTS soil_samples (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id      INT UNSIGNED NOT NULL,
  sampled_at    DATE NOT NULL,
  lat           DECIMAL(10,7) NULL,
  lon           DECIMAL(10,7) NULL,
  depth_cm      TINYINT UNSIGNED NULL,
  soil_type     VARCHAR(80) NULL,
  laboratory    VARCHAR(160) NULL,
  collected_by  INT UNSIGNED NULL,
  notes         TEXT NULL,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_soil_field (field_id, sampled_at),
  CONSTRAINT fk_soil_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_soil_user FOREIGN KEY (collected_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- value_status separates a laboratory result from an estimate. An estimated value
-- presented as a measurement is the failure mode this column exists to prevent.
CREATE TABLE IF NOT EXISTS soil_measurements (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sample_id      INT UNSIGNED NOT NULL,
  analyte        VARCHAR(40) NOT NULL,
  value          DECIMAL(12,4) NULL,
  unit           VARCHAR(20) NULL,
  method         VARCHAR(120) NULL,
  value_status   ENUM('MEASURED','IMPORTED','ESTIMATED','MODEL_DERIVED','DEMO')
                 NOT NULL DEFAULT 'MEASURED',
  is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_sample_analyte (sample_id, analyte),
  CONSTRAINT fk_meas_sample FOREIGN KEY (sample_id) REFERENCES soil_samples(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------------- irrigation

CREATE TABLE IF NOT EXISTS irrigation_sources (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(160) NOT NULL,
  kind        ENUM('canal','pump','rainfed','deep_well','creek','other') NOT NULL,
  lat         DECIMAL(10,7) NULL,
  lon         DECIMAL(10,7) NULL,
  notes       TEXT NULL,
  is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS irrigation_channels (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_id      INT UNSIGNED NULL,
  name           VARCHAR(160) NULL,
  kind           ENUM('supply','drainage') NOT NULL DEFAULT 'supply',
  path_geojson   JSON NULL,
  is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_chan_source FOREIGN KEY (source_id) REFERENCES irrigation_sources(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS irrigation_zones (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name             VARCHAR(160) NOT NULL,
  boundary_geojson JSON NULL,
  source_id        INT UNSIGNED NULL,
  is_demo          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_zone_source FOREIGN KEY (source_id) REFERENCES irrigation_sources(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS field_irrigation_links (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id     INT UNSIGNED NOT NULL,
  zone_id      INT UNSIGNED NULL,
  channel_id   INT UNSIGNED NULL,
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_field_zone (field_id, zone_id, channel_id),
  CONSTRAINT fk_fil_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_fil_zone FOREIGN KEY (zone_id) REFERENCES irrigation_zones(id),
  CONSTRAINT fk_fil_channel FOREIGN KEY (channel_id) REFERENCES irrigation_channels(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------- terrain

CREATE TABLE IF NOT EXISTS terrain_sources (
  id                 INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name               VARCHAR(160) NOT NULL,
  provider           VARCHAR(120) NULL,
  acquired_on        DATE NULL,
  resolution_m       DECIMAL(8,3) NULL,
  vertical_datum     VARCHAR(80) NULL,
  licence            VARCHAR(160) NULL,
  is_demo            BOOLEAN NOT NULL DEFAULT FALSE,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS terrain_tiles (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_id     INT UNSIGNED NOT NULL,
  bounds_geojson JSON NULL,
  file_path     VARCHAR(512) NULL,
  min_elev_m    DECIMAL(8,2) NULL,
  max_elev_m    DECIMAL(8,2) NULL,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_tile_source FOREIGN KEY (source_id) REFERENCES terrain_sources(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------- weather

CREATE TABLE IF NOT EXISTS weather_observations (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id       INT UNSIGNED NULL,
  observed_at    DATETIME NOT NULL,
  rainfall_mm    DECIMAL(7,2) NULL,
  temp_c         DECIMAL(5,2) NULL,
  humidity_pct   DECIMAL(5,2) NULL,
  wind_ms        DECIMAL(5,2) NULL,
  source         VARCHAR(80) NOT NULL DEFAULT 'NullProvider',
  value_status   ENUM('MEASURED','IMPORTED','ESTIMATED','MODEL_DERIVED','DEMO')
                 NOT NULL DEFAULT 'IMPORTED',
  is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_weather_field_time (field_id, observed_at),
  CONSTRAINT fk_weather_field FOREIGN KEY (field_id) REFERENCES fields(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------------- risk / forecast

CREATE TABLE IF NOT EXISTS risk_predictions (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id      INT UNSIGNED NOT NULL,
  condition_id  INT UNSIGNED NULL,
  computed_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  risk_score    DECIMAL(6,4) NULL,
  risk_band     ENUM('LOW','MODERATE','HIGH','INSUFFICIENT_DATA') NOT NULL,
  method        VARCHAR(120) NOT NULL,
  model_version VARCHAR(120) NOT NULL,
  inputs_json   JSON NULL,
  capability_status ENUM('EXPERIMENTAL','NOT_VALIDATED','VALIDATED')
                NOT NULL DEFAULT 'NOT_VALIDATED',
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_risk_field (field_id, computed_at),
  CONSTRAINT fk_risk_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_risk_condition FOREIGN KEY (condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS forecasts (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  field_id        INT UNSIGNED NOT NULL,
  condition_id    INT UNSIGNED NULL,
  computed_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  horizon_days    SMALLINT UNSIGNED NOT NULL,
  predicted_value DECIMAL(12,4) NULL,
  uncertainty     DECIMAL(12,4) NULL,
  method          VARCHAR(120) NOT NULL,
  model_version   VARCHAR(120) NOT NULL,
  inputs_json     JSON NULL,
  status          ENUM('PREDICTED','INSUFFICIENT_DATA') NOT NULL DEFAULT 'INSUFFICIENT_DATA',
  capability_status ENUM('EXPERIMENTAL','NOT_VALIDATED','VALIDATED')
                  NOT NULL DEFAULT 'NOT_VALIDATED',
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_forecast_field (field_id, computed_at),
  CONSTRAINT fk_fc_field FOREIGN KEY (field_id) REFERENCES fields(id),
  CONSTRAINT fk_fc_condition FOREIGN KEY (condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------- sensors

CREATE TABLE IF NOT EXISTS sensor_devices (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(160) NOT NULL,
  kind          VARCHAR(60) NOT NULL,
  field_id      INT UNSIGNED NULL,
  provider      VARCHAR(60) NOT NULL DEFAULT 'NullProvider',
  installed_on  DATE NULL,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  is_demo       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sensor_field FOREIGN KEY (field_id) REFERENCES fields(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sensor_readings (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  device_id    INT UNSIGNED NOT NULL,
  observed_at  DATETIME(3) NOT NULL,
  metric       VARCHAR(40) NOT NULL,
  value        DECIMAL(14,4) NULL,
  unit         VARCHAR(20) NULL,
  value_status ENUM('MEASURED','IMPORTED','ESTIMATED','MODEL_DERIVED','DEMO')
               NOT NULL DEFAULT 'MEASURED',
  is_demo      BOOLEAN NOT NULL DEFAULT FALSE,
  KEY ix_reading_device (device_id, observed_at),
  CONSTRAINT fk_reading_device FOREIGN KEY (device_id) REFERENCES sensor_devices(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------ research registry

CREATE TABLE IF NOT EXISTS experiments (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code            VARCHAR(40) NOT NULL,
  hypothesis      TEXT NOT NULL,
  dataset_version VARCHAR(120) NULL,
  model_version   VARCHAR(120) NULL,
  random_seed     INT NULL,
  configuration   JSON NULL,
  metrics         JSON NULL,
  output_path     VARCHAR(512) NULL,
  status          ENUM('PLANNED','RUNNING','COMPLETE','ABANDONED')
                  NOT NULL DEFAULT 'PLANNED',
  is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_experiment_code (code),
  KEY ix_experiment_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS datasets (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  version           VARCHAR(120) NOT NULL,
  manifest_path     VARCHAR(512) NULL,
  annotation_version VARCHAR(120) NULL,
  class_list        JSON NULL,
  split_rule        VARCHAR(120) NOT NULL DEFAULT 'field_level',
  frozen            BOOLEAN NOT NULL DEFAULT FALSE,
  is_demo           BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_dataset_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS dataset_images (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  dataset_id  INT UNSIGNED NOT NULL,
  image_id    INT UNSIGNED NOT NULL,
  field_id    INT UNSIGNED NOT NULL,
  split       ENUM('train','validation','test') NOT NULL,
  is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE KEY uq_dataset_image (dataset_id, image_id),
  KEY ix_dataset_split (dataset_id, split, field_id),
  CONSTRAINT fk_di_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id),
  CONSTRAINT fk_di_image FOREIGN KEY (image_id) REFERENCES images(id),
  CONSTRAINT fk_di_field FOREIGN KEY (field_id) REFERENCES fields(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS annotation_reviews (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  annotation_id  INT UNSIGNED NOT NULL,
  reviewer_id    INT UNSIGNED NOT NULL,
  agrees         BOOLEAN NOT NULL,
  corrected_condition_id INT UNSIGNED NULL,
  notes          TEXT NULL,
  is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
  reviewed_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_review_annotation (annotation_id),
  CONSTRAINT fk_rev_annotation FOREIGN KEY (annotation_id) REFERENCES annotations(id),
  CONSTRAINT fk_rev_user FOREIGN KEY (reviewer_id) REFERENCES users(id),
  CONSTRAINT fk_rev_condition FOREIGN KEY (corrected_condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- jobs already exists (migration 003). Only the is_demo column is missing.
SET @col := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'jobs' AND COLUMN_NAME = 'is_demo'
);
SET @ddl := IF(@col = 0,
  'ALTER TABLE jobs ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT FALSE',
  'DO 0');
PREPARE s1 FROM @ddl; EXECUTE s1; DEALLOCATE PREPARE s1;
