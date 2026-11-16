-- AGRISCAN p33 — migration 013: what the phone says it is doing.
--
-- "Expired, 0 frames, the phone never picked this up" had two causes that looked
-- identical from the dashboard: the phone was not polling at all, or it was polling but
-- ignoring the command. The second is a fault in the phone's own state, and nothing on
-- the server could see it.
--
-- The phone now reports the session it believes it is running on every poll, and that is
-- stored here. "Polling, and says it is idle, while a session is armed" is a sentence the
-- dashboard can now say out loud.
ALTER TABLE capture_devices
  ADD COLUMN IF NOT EXISTS reported_session_id BIGINT UNSIGNED NULL AFTER preview_requested_at,
  ADD COLUMN IF NOT EXISTS reported_state VARCHAR(20) NULL AFTER reported_session_id;
