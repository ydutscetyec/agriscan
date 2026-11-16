# AGRISCAN p6 — changes since p5

## Track B (finished)

- Migration 007: 22 storage tables for hardware and data not yet connected
  (telemetry, RTK, spectral bands, soil, irrigation, terrain, weather, risk, forecasts,
  sensors, experiments, datasets). All carry `is_demo`. All empty by design.
- `app/providers/`: 11 provider interfaces, each defaulting to a Null implementation
  that reports HARDWARE_REQUIRED or DATA_REQUIRED and never invents a value.
- `app/services/mission_planner.py`: GSD = (H x s) / f, lawnmower waypoints, estimated
  flight time and battery count, QGroundControl WPL export. Camera parameters are
  configuration (`AGRISCAN_CAMERA_*`). Every output labelled ESTIMATED.
- `app/services/spectral.py`: NDVI, GNDVI, NDRE, NDWI. Each raises on an RGB-only
  image rather than returning a number.
- `app/services/risk.py`: RiskModel and ForecastModel, returning INSUFFICIENT_DATA.
- `scripts/validate_split.py`: exits 1 if any field appears in two splits; enforces
  the 150-sample / 3-field / 2-visit-date minimum per class.
- `scripts/backup.sh` + `docs/RESTORE.md`.
- `/trackb/*` API endpoints. **No dashboard navigation entry** for any Track B module.

## The seven gaps

1. **`.env` now loads.** `app/config.py` calls `load_dotenv()` on the backend `.env`.
   Shell variables still win (`override=False`). You can drop the `$env:` lines.
2. **Upload page** (`/upload`): drag-and-drop, multiple files, preview, per-file
   validation, real upload progress (XHR), sequential uploads for weak connections.
3. **Pagination** on Detections: 50 per page, "Showing 51–100 of 340", previous/next.
   `/detections` now returns `total`.
4. **Analytics page** (`/analytics`): confusion matrix, per-class precision / recall /
   F1, agreement rates. Metrics are **withheld below 30 verified pairs**
   (`AGRISCAN_METRICS_MIN_VERIFIED`) with the message "Metrics unavailable —
   insufficient validated samples." Counts are always shown.
5. **Admin user creation** on the Users page, with role descriptions and a warning
   before granting the technician role.
6. **Delete field** for admins, with confirmation. The server **refuses (409)** if the
   field has images or flights, so research data cannot be orphaned.
7. **Double-submit guards.** Fields form now disables while saving. The field client's
   Capture button had **no guard** — a double-tap saved two captures. Fixed.

## Also

- Fields warn when a drawn boundary exceeds 20 ha ("check boundary"). Rice parcels
  around Surallah are typically 0.5–1.5 ha; a larger figure is almost always a
  mis-drawn polygon.
- Analytics carries a sampling caveat: the review queue over-samples hard cases, so
  metrics on the reviewed set are not model performance. Report that from held-out
  test fields.

## Tests

Backend 162 passing (was 116). Frontend 12 passing. `npm run build` clean.
