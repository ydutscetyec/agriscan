-- AGRISCAN p31 — migration 012: flight video kept alongside the stills.
--
-- The stills stay the detection and dataset source: full resolution, EXIF GPS written
-- by the camera. The video is the reviewable record of the whole flight — continuous,
-- no gaps between frames — and a place to go back to for a spot the interval missed.
--
-- A frame pulled out of that video is NOT equivalent to a still. It is roughly a sixth
-- of the pixels, inter-frame compressed, and its position is interpolated from a 1 Hz
-- track rather than recorded by the camera. Both facts are carried on the image row so
-- nothing derived from video can be mistaken for ground truth later.

ALTER TABLE capture_sessions
  ADD COLUMN IF NOT EXISTS video_path VARCHAR(512) NULL,
  ADD COLUMN IF NOT EXISTS video_bytes BIGINT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS video_duration_s DECIMAL(8,2) NULL,
  ADD COLUMN IF NOT EXISTS video_mime VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS video_uploaded_at DATETIME NULL,
  ADD COLUMN IF NOT EXISTS track_path VARCHAR(512) NULL,
  ADD COLUMN IF NOT EXISTS track_points INT UNSIGNED NULL;

-- 'video_interpolated' marks a position worked out from the flight track, not read from
-- the file. Keeping it a distinct value rather than reusing 'manual' means a query can
-- always exclude it from anything that reports accuracy.
ALTER TABLE images
  MODIFY COLUMN gps_source
    ENUM('exif','apm_log','manual','device','missing','video_interpolated')
    NOT NULL DEFAULT 'missing';

-- Which video frame an image came from, when it came from one at all.
ALTER TABLE images
  ADD COLUMN IF NOT EXISTS from_video_offset_s DECIMAL(8,2) NULL;

CREATE INDEX IF NOT EXISTS ix_images_from_video ON images (capture_session_id, from_video_offset_s);
