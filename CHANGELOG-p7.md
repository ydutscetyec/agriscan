# AGRISCAN p7 — changes since p6

## Drone camera: the website controls the phone on the drone

Two new pages:

- **/drone-camera** (dashboard, technician and admin): paired phones with live battery,
  location accuracy and camera status; start a session with field, interval, time limit
  and optional frame limit; an interval helper that works out the frame interval from
  altitude, speed and overlap; session history with frame counts and why each ended.
- **/camera** (open on the drone phone): pairs once, then waits. When a session starts
  it opens the rear camera, captures on its interval, tags each frame with the phone's
  GPS, keeps the screen awake, and stops itself at the time or frame limit.

**Design rule: the link will drop in the air.** Start the session on the ground before
takeoff. After that the phone needs no connection: it times frames by its own clock,
stops by itself, and uploads after landing. The dashboard can stop a session early only
if it can still reach the phone.

### Geotagging changes — update Chapter 3

Frames captured by a browser have **no EXIF GPS**. For drone-camera frames, the phone's
geolocation at the moment of capture is now the position of record
(`gps_source = device_geolocation`, with the reported accuracy in metres). The APM flight
log remains the cross-check. Phone photos taken through the normal camera app still use
EXIF as before.

### Image quality depends on the phone

Where the browser supports `ImageCapture.takePhoto()` (Chrome on Android), frames are
full-resolution stills. Otherwise they are grabbed from the video stream at lower
resolution. The station shows which mode it is in. Check it before a survey.

## Field boundaries page (/field-boundaries)

Every mapped field on one map, with a list beside it. Each field is shown as a thumbnail
of its **actual drawn boundary**, with area, variety, growth stage and day since planting,
image count, and verified-versus-total detections. Select a field to fly to it. Fields
without a boundary are listed separately.

## Bugs fixed

1. **Saved boundaries could not be removed** (reported). The field being edited was drawn
   twice — once by the editor, once from its saved copy — so clearing it appeared to do
   nothing. The saved copy is now hidden while editing, and each field has a
   **Remove boundary** button that works without the edit form.
2. Clicks kept adding corners after a ring was closed.
3. Closing with a double-click added two stray corners at the same spot.
4. Every re-save of a boundary added a duplicate corner.
5. **The service worker served stale app code in development.** It cached source modules
   cache-first — very likely why the dashboard still showed the p5 sidebar after
   installing p6. It now registers in production builds only and clears itself in
   development. It never caches live API data.
6. Protected images failed to load on the detection and verification pages: an `<img>`
   tag cannot send the sign-in token. Images now load through an authenticated fetch.
7. After signing in, the app always went to the dashboard. It now returns to the page
   you came from — so the drone phone lands back on /camera.

Also added: **Undo last corner** while drawing, and clicking a saved boundary on the
Manage fields map opens it for editing.

## Look and feel

- Sidebar icons, grouped as Monitoring, Capture, Fields, Analysis, Administration.
- A drawn brand mark: paddies from the air with a scan bracket.
- Overview opens with the **verification pipeline** — images captured, model detections,
  awaiting review, technician verified — since that path is what AGRISCAN is about.
- Page headers with a one-line purpose on every main page; KPI tiles whose left edge
  colour matches the detection status; empty states that say what to do next.
- Tabular numerals throughout, so figures line up.

## Tests

Backend 185 passing (was 162). Frontend 15 passing (was 12). Build clean.
Not tested here: anything needing a real phone — camera, GPS, wake lock, HTTPS pairing.
