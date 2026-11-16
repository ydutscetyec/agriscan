# AGRISCAN p22 — intro splash and role guides

Extract over p21. Frontend only, plus one line in `app/site.py`. **Keep your
`backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration this time. If you have not applied p21's yet, that is still
`python -m migrations.run_migrations` in `backend` — the sign-in error you saw was a
database missing that migration.

## The intro video

Plays once, on the first visit to a device, over whatever page is loading underneath.

It is a splash, not a loading gate. The app loads behind it and is ready long before the
ten seconds are up, so nothing is being delayed. **Skip**, Escape, or a tap anywhere
ends it immediately.

Once per device is deliberate. An intro on every visit would cost a farmer the download
each time and put ten seconds between them and photographing a plant. To make a new
intro play for everyone, raise `VERSION` in `src/components/Splash.jsx`.

What was done to the file you sent:

| | Before | After |
|---|---|---|
| MP4 (H.264) | 497 KB, with audio | 181 KB, silent, faststart |
| WebM (VP9) | — | 212 KB |
| Poster frame | — | 9 KB |

- **Audio removed.** Browsers refuse to autoplay anything with sound, so the video would
  have sat on its first frame. There is now no audio track at all.
- **Faststart**, so it begins playing while still downloading instead of after.
- **Two codecs.** H.264 is what iOS and Safari need. Some Chromium builds ship without a
  licensed H.264 decoder, including on Android — the test browser here is one of them,
  and with MP4 alone it played nothing. VP9/WebM covers those; each browser picks what
  it can play.
- **Never on `/camera`.** That screen is opened with the aircraft already powered.

Every failure path ends with the splash closing, never a stuck white screen: codec
unsupported, autoplay refused, nothing playing after 2.5 s, or 12 s elapsed. The
animation's own background is white and so is the backdrop, so on a wide monitor there
is no visible letterbox — one white screen with the animation centred.

People who have asked their phone or computer for reduced motion do not get it at all.

## Onboarding guide

Opens by itself the first time an account signs in, and is on the **?** button after
that — in the dashboard top bar, and in the field client header.

Each role gets its own steps, because they do different jobs:

- **Farmer** (5, bilingual titles): what AGRISCAN does · taking a usable photo · a result
  is pending until a technician checks it · confirming whether it matches · photos keep
  working with no signal
- **Technician** (5): you are the gate between the model and the farmer · the queue · why
  severity is yours and not the model's · recommendations need approval · the drone
  camera needs HTTPS
- **Admin** (5): how a photo becomes advice · set up fields and farmers before the first
  flight · nothing is analysed without a model in production · roles · what to do before
  going public
- **Researcher** (3): detection versus verified detection · capability status · what not
  to claim

Stepped cards, not a tour that points at things on the page. A pointing tour has to find
a real element; it breaks silently when a page is renamed, and on a phone the thing it
points at is usually off screen.

"Already seen" is kept per device **and per account**, so a farmer borrowing a
technician's phone gets their own guide. It is not in the database: that avoids another
migration and another endpoint, at the cost of replaying if someone clears their browser
data. Harmless, and the **?** button means the flag is never the only way back in.

The five new farmer strings are in `HILIGAYNON-REVIEW.csv` for a first-language speaker
to check, like the rest.

## Also

- `.mp4` and `.jpg` are now given explicit MIME types by the server, for the same reason
  `.js` already was: some Windows machines map them wrongly in the registry.
- The existing content-security policy already allowed this (`media-src 'self'`), and the
  browser check confirmed no blocked resources.

## Tests

Backend 308 passing, unchanged. Frontend **25 passing** (15 + 10 new in
`src/__tests__/onboarding.test.js`): when the intro may play, the `/camera` exclusion,
reduced motion, storage being unavailable, and that every role's steps have an icon, a
heading and a body.

Checked in a real browser: the video plays and is muted, Skip works, it does not return
on a second visit, each role's guide opens once and is replayable, Escape closes it, the
phone layout does not scroll sideways, and `/camera` never shows the splash.
