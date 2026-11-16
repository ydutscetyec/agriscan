# AGRISCAN p26 — three bugs fixed, and the missing images page

Extract over p25. Frontend only. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration.

## 1. The sound button sat on top of Skip

p22 styled the Skip button as an absolutely positioned element pinned to the top right.
p23 put both buttons in a row and gave Skip a class name that still matched that old
rule, so Skip was pulled out of the row and the speaker button was laid on top of it.

The stale rule is gone. Measured in the browser: **Tap for sound** and **Skip** sit side
by side with no overlap. The dead CSS from the p22 guide card went with it — about 3.5 KB
of rules nothing had used since p23.

## 2. Signing out of the farmer account made admin sign-in impossible

This was a real bug and a bad one. The tour keeps running after sign-out.

It navigates on every step — that is how it walks you through the pages — and nothing
stopped it when the user went away. So after signing out of the farmer account the tour
was still open and still calling `navigate('/field')` every ten to fifteen seconds. Each
one bounced off the sign-in guard and reloaded the sign-in page, wiping whatever had been
typed. If you were mid-password when a step fired, the form emptied under you.

The tour now closes the moment there is no signed-in user, and will not navigate or
render without one.

Verified: sign in as the farmer, leave the tour running, sign out, type the admin name
and password, wait fifteen seconds — the text is still there and the sign-in works.

## 3. "1 image captured" that you could not open

Not a bug in the count. There was nowhere to go and look.

**Detections** lists model output only. A photo that has arrived but has no detection yet
— because it is queued, because no model is in production, because the quality gate
rejected it, or because the palay gate decided it was not rice — existed as a number on
the Overview and on no screen at all.

New page, **Captured images**, in the sidebar under Capture. Every photo on the server
with its thumbnail, field, source, capture time, quality flag, and what is happening to
it:

| Status | What it means |
|---|---|
| Waiting | In the queue, nothing analysing it. Check the worker is running |
| Analysing | A worker has it now |
| Analysed | The model has finished |
| Failed | The worker could not finish; the worker log says why |
| Not queued | No analysis job exists for this photo at all |

Your image is almost certainly **Waiting**, because no model is in production yet. That
is the expected state until you register trained weights; the photo is safe and will be
analysed when a model and a worker exist.

If the thumbnail says **no file**, the row is in the database but the JPEG is not on disk
where `AGRISCAN_IMAGE_ROOT` points — which is the one case worth investigating.

The page also joins the tour, so an admin tour is now 17 steps.

## 4. Connecting the drone phone

Two different things, often confused:

**A farmer's own phone** needs nothing special. They open the site, sign in, and the
field client opens with Take a photo. Any phone, any browser.

**The phone mounted on the drone** is the capture station:

1. The site must be on **https**. Over plain `http://` the browser refuses the page the
   camera and GPS entirely — this is the single most common reason it does not work. Use
   the Cloudflare Tunnel address from `DEPLOY.md`. `localhost` on the laptop counts as
   secure; the laptop's `192.168.x.x` address does not.
2. On the drone phone, open that https address, sign in as a technician or admin, and go
   to **/camera**. Allow camera and location when asked. Leave that page open and the
   screen on; it holds a wake lock so it will not sleep.
3. On the laptop, open **Drone camera** on the dashboard. The station appears there.
   Arm the session and trigger captures; photos arrive and appear under Captured images.

If the phone shows the insecure-page warning instead of a camera, it is step 1. If the
station never appears on the dashboard, the phone is signed in as a different account or
is on a different address than the laptop is serving.

## Tests

Frontend 30 passing (the tour test now expects the new page). Backend untouched; 308
passing.

Checked in a real browser: the splash buttons no longer overlap, the farmer-sign-out then
admin-sign-in sequence works with a fifteen-second wait in the middle, and Captured images
lists a queued photo as Waiting with its field, source and time, including the "no file"
case when the JPEG is missing from disk.
