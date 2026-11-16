# AGRISCAN p27 — delete photos, tour on every sign-in

Extract over p26. **Keep your `backend\.env`.**

```powershell
cd backend; .venv\Scripts\activate
cd ..\web; npm ci; npm run build
```

No migration.

## Deleting a captured photo

Admins get a delete button on each card in **Captured images**. It asks first, then
removes the file from disk and every row derived from it — detections, jobs,
annotations, bands, RTK observations, dataset membership — in dependency order, because
all of those foreign keys are `RESTRICT` and a missed one would fail rather than corrupt.

Two rules it will not bend:

- **A photo with technician-verified results cannot be deleted.** A verified detection is
  the ground truth your reported accuracy is measured against, so removing one silently
  changes a number in Chapter 4. To discard a bad *result*, reject it in the verification
  queue. Delete is for photos that should never have been in the dataset — a test shot, a
  misfire, a picture of someone's shoe.
- **The deletion is recorded.** `audit_log` is append-only by migration 002, so what was
  deleted, by whom and when survives the thing it describes.

The database comes first and the file second: a file left on disk is a smaller problem
than a row pointing at a file that is gone. If the JPEG was already missing — like your
`#1`, which shows **no file** — the row is still removed and the message says so.

Six new backend tests cover all of it, including that a non-admin gets 403.

## The tour now opens by itself on every sign-in

It did not before, because you had already finished it once and it was marked seen.

It now opens every time someone signs in, and starts advancing on its own immediately.

It is tied to **signing in**, not to loading a page — and that distinction turned out to
matter. My first attempt keyed it to the page load, and reloading anywhere in the app
threw the tour back up and navigated you to the Overview. Pressing F5 on Captured images
bounced you to the dashboard every time. Caught in testing, fixed: a restored session
after a reload leaves the tour alone, and only a sign-in through the form starts it.

`START_EVERY_SIGN_IN` in `src/components/Onboarding.jsx` turns it back to once per
account per device.

## The sound, again — and how to make it work for your defence

Nothing changed in the code here, because there is nothing left to change. The intro
already asks for sound on every load, falls back to muted when refused, and unmutes on
the first touch anywhere.

I tested the same build in the same browser with autoplay policy relaxed:

| Chromium, default policy | starts muted |
| Chromium, `--autoplay-policy=no-user-gesture-required` | **starts unmuted and playing** |

Same page, same video, same code. The only thing standing between you and automatic
sound is the browser's policy, and it is not reachable from a website.

For a defence or a demo, pick whichever is easiest:

- **Edge** (simplest): Settings → Cookies and site permissions → Media autoplay → Allow,
  for your site. Then it plays with sound on every load, no flag, no tapping.
- **Chrome, launched for the demo:**
  `chrome.exe --autoplay-policy=no-user-gesture-required http://localhost:5173`
  Make a desktop shortcut with that target. This is exactly what I tested.
- **Chrome, normally:** install the site as an app from the address bar, or just keep
  using it — Chrome's per-site media engagement score rises with each visit where the
  video actually plays, and then permits it by itself.

On a farmer's phone, expect the first tap. There is no setting on iOS at all.

## Your expenses document

Read it. Three things worth correcting before it goes in the paper:

1. **The hosting rows are labelled "One-time cost" but they are monthly.** ₱679/month +
   ₱75/month = ₱754, shown as a one-time ₱754. Over a year that is ₱9,048, not ₱754.
2. **The summary says "Hosting per month 0" and then adds ₱754 to the total anyway.**
   16,114 + 754 = 16,868, so the total silently includes one month of the hosting the row
   above says is free.
3. **The ₱679/month cloud hosting is an alternative to Cloudflare Tunnel, not an
   addition.** Your deployment plan runs the server on the laptop behind the free tunnel,
   so if you keep that plan the honest figure is **₱16,114 total, ₱0 recurring**, with a
   domain at roughly ₱900 a year only if you want a permanent address.

The cleanest fix is a summary with two lines: one-time ₱16,114, and recurring ₱0 (or ₱75
a month if you buy a domain), with the VPS listed separately as an option you did not
take. A panel is more likely to ask why a cost appears than why one does not.

## Tests

Backend **314 passing** (308 + 6 new). Frontend 30 passing.

Checked in a real browser: the tour opens and auto-advances on sign-in, a reload on
Captured images no longer hijacks navigation, the tour opens again on the next sign-in,
deleting a photo removes the card and reports the missing file honestly, and the intro
plays unmuted by itself under a relaxed autoplay policy.
