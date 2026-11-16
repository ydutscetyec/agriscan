# AGRISCAN p23 — intro on every visit, sound, full page tour

Extract over p22. Frontend only. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration. (If sign-in still fails with "Internal server error", p21's migration is
the one that is missing: `python -m migrations.run_migrations` in `backend`.)

## The intro now plays every time

Every page load, not once per device. Skip, Escape, or a tap anywhere still ends it
immediately, and that exit matters more now, so it is a solid button in the corner from
the first frame.

Two costs worth knowing, neither of them fatal:

- **Ten seconds between a person and their work**, every reload. A farmer who mistypes
  a password and reloads sits through it again. The Skip button is the whole answer to
  this, so do not move it or make it subtle.
- **Bandwidth only on the first load.** The video is a hashed build asset cached for a
  year and also kept by the service worker, so a refresh replays it from disk, not from
  the network. First load on mobile data costs one file: 509 KB (H.264) or 752 KB (VP9),
  whichever the browser picks — never both.

To go back to once per device, set `PLAY_EVERY_VISIT = false` at the top of
`src/components/Splash.jsx`. Nothing else changes.

Still never on `/camera`, and still skipped for anyone whose device asks for reduced
motion.

## Quality

p22 shipped a re-encode of your file at a compression setting that was too aggressive.
That was my mistake. p23 ships **your original video, untouched** — the same video and
audio streams, with only the index moved to the front of the file so it starts playing
before it has finished downloading.

| | p22 | p23 |
|---|---|---|
| MP4 (H.264) | 181 KB, re-encoded, silent | **509 KB, your file as sent** |
| WebM (VP9) | 212 KB, silent | 752 KB, SSIM 0.9997 against your file |
| Poster | quality 6 | quality 2 |

This is now the ceiling. The MP4 is your file, so nothing on this side can improve it
further. The source is 576×1248 at about 400 kbps, which is modest for that frame size —
if you want it genuinely sharper, re-export it from whatever made the animation at a
higher bitrate (try 2–3 Mbps) and ideally 1080×2340, then send that file and I will drop
it in. Re-encoding what I have would only add artefacts.

## Why it had no music, and what it has now

Browsers **refuse to autoplay video with sound**. Chrome, Safari, Firefox and Edge all
block it, and on iOS it is absolute. This is not a setting; it is a deliberate rule,
because autoplaying audio was abused badly enough that every vendor killed it. A page
that tries gets its `play()` rejected and sits frozen on the first frame — which is why
p22 removed the audio track rather than ship a splash that might not move.

The rule has one exception: **sound is allowed after the person interacts with the page.**
So:

- The audio track is back in both files.
- The splash starts **muted** and plays. A speaker button sits next to Skip.
- Tapping it is the interaction the browser requires, so the sound comes on at once.
- The choice is remembered. On later visits the splash tries to start unmuted; if the
  browser refuses, it falls back to muted without a pause and the speaker button is
  still there.

In practice: on a desktop Chrome that you use often, it will usually start with sound
from the second visit onward. On a phone, and on Safari anywhere, expect it to stay
muted until tapped. There is no way around that, from any website.

## The guide is now a tour of every page

It drives the app: each step opens a real page and explains the page you are looking at,
with the panel docked in the corner — bottom right on a desktop, a sheet at the bottom on
a phone — so the page stays visible and usable behind it.

- **Admin**: all 16 pages, in sidebar order — Overview, Map, Detections, Verification
  queue, Recommendations, Drone camera, Flight records, The aircraft, Upload images,
  Field boundaries, Manage fields, Farmers, Analytics, Models, Users, Your account.
- **Technician**: the same minus Users.
- **Researcher**: minus Users and Drone camera.
- **Farmer**: the three field-client pages, with bilingual headings.

Steps are filtered using the same role lists `App.jsx` enforces on the routes, so nobody
is ever walked into a page that will refuse them. A test checks that directly.

It is keyed on routes, not on page elements. A spotlight tour has to find an element by
selector; it breaks silently when a card moves or is renamed, and on a phone it usually
points at something off screen. A route either exists or it does not.

Opens by itself on an account's first sign-in, and is on the **?** button after that.

## Bug found while building it

**The tour could not get past its second page.** `RequireAuth` renders its own
`<AppShell>` for every route, so the shell is destroyed and rebuilt on each navigation.
The tour's step number lived in the shell, so the tour's own navigation reset it to 1,
forever. The state now lives above the router in a context, which is where any state
that has to outlive a navigation belongs.

Worth remembering for anything else page-spanning you add later — a multi-page form, a
running upload indicator — the shell is not a safe place to keep it.

## Tests

Frontend **27 passing** (15 + 12). New or changed: the intro plays on every visit, the
`/camera` exclusion, reduced motion, storage unavailable, the sound preference, that the
admin tour covers all 16 pages, that no role is sent to a page its route would refuse,
that the farmer tour stays inside `/field`, and that no tour repeats a page.

Backend untouched this round; 308 passing as of p22.

Checked in a real browser: the splash plays and replays on reload, the speaker button
unmutes and the preference is stored, the admin tour walks all 16 pages in order with no
page crashing, the farmer tour covers its three pages on a phone without the panel
covering the tab bar or the page scrolling sideways, and the **?** button replays it.
