-- AGRISCAN p30 — migration 011
--
-- capture_devices.preview_requested_at
--   The viewfinder tells the phone to send frames only while an operator is watching.
--   That "someone is watching" flag was held in a Python dictionary, which is private to
--   one server process. With a dev server on one port and serve.py on another — or any
--   future second worker — the dashboard set the flag on one process while the phone
--   polled another, so the phone was never asked and the viewfinder waited forever.
--   State two processes must agree on belongs in the database.
--
-- capture_sessions.frames_reported / last_report_at
--   What the phone last told us, so a session that produced nothing can be told apart
--   from a session the phone never picked up at all.

ALTER TABLE capture_devices
  ADD COLUMN IF NOT EXISTS preview_requested_at DATETIME NULL AFTER last_seen_at;

ALTER TABLE capture_sessions
  ADD COLUMN IF NOT EXISTS last_report_at DATETIME NULL;
