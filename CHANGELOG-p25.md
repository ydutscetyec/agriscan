# AGRISCAN p25 — tour runs itself, sidebar scroll fix, sound on first touch

Extract over p24. Frontend only. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration.

## Fixed: Models and Users could not be seen at steps 14–15

The sidebar is taller than a short screen, so its last links sit below its own fold. The
tour pointed at them correctly, but at a link the person could not see — on a 1366×640
screen the Users link is 775 px down a 640 px window.

The tour now scrolls the sidebar so the link it is pointing at is on screen before
measuring. It uses `block: 'nearest'`, which leaves an already-visible link alone, so
nothing jumps between steps.

Also fixed while verifying it: the highlight ring is drawn 6 px outside the control, and
a sidebar link starts at x = 0, so the ring's left border was being drawn off the edge
of the screen. It is now clamped to the viewport.

Verified on 1366×640 — the worst case among common laptop screens: all 16 rings fully on
screen, each landing on its own link, no page errors.

## The tour now plays itself

It advances on its own, with no clicking. Each step is timed from how much there is to
read — about 3.2 words a second, so roughly 11–15 s for these steps — with a 7 s floor so
a short step is never a flash and a 20 s ceiling so a long one cannot hold someone who
has stopped reading.

- The bar under the text is the timer, so what is about to happen is visible rather than
  a surprise. The dark part is steps already done; the lighter part is the one running.
- A **pause/play** button sits next to Back and Next.
- Pressing **Back** or **Next** pauses it. Someone steering by hand should not be shoved
  onward mid-sentence; press play to hand it back.

A full admin tour runs about three minutes unattended. `AUTO_ADVANCE`,
`READING_WORDS_PER_SECOND`, `MIN_STEP_MS` and `MAX_STEP_MS` at the top of
`src/components/Onboarding.jsx` control all of it.

## Sound: what changed, and what still cannot

The intro now turns its sound on at **the first touch, click or key press anywhere on the
page** — not just on the speaker button. On a phone that means the first tap anywhere on
the video, and that tap no longer closes the intro; Skip is there for closing it.

I could not make it play with sound on a fresh browser with no interaction at all, and
neither can any website. Browsers reject `play()` on an unmuted video until the person
has interacted with the page or the browser has decided the site has earned it. There is
no flag, no header, and no HTML attribute that overrides it. A page that tries anyway
gets a rejected promise and a frozen first frame, which is worse than silence.

Where it *will* start with sound and nothing pressed:

- **Chrome and Edge on your laptop, after a few visits.** Both keep a media engagement
  score per site; once it is high enough they allow unprompted audio and it simply works.
  Opening the site a handful of times and letting the intro run gets you there.
- **Edge, immediately, if you set it:** Settings → Cookies and site permissions → Media
  autoplay → add your site → Allow.
- **Firefox:** padlock in the address bar → Permissions → Autoplay → Allow Audio and Video.
- **Chrome, immediately:** install the site as an app (the manifest from p22 is already
  there — address bar install icon). Chrome grants installed apps autoplay with sound.
- **Safari and iPhone:** Safari → Settings for This Website → Auto-Play → Allow All
  Auto-Play. On iPhone there is no such setting; the first tap is the only way.

For a defence demo on your own laptop, the Edge setting or installing it as an app makes
it unconditional. For a farmer opening the link for the first time on a phone, expect
the first tap.

### Bug found while building this

The first tap turned the sound on *and* closed the intro. The window-level listener fires
on `pointerdown`, React re-renders, and by the time the matching `click` arrives the
handler is a new one that no longer knows the sound had just been unblocked, so it took
the dismiss branch. The unlocking gesture is now timestamped and ignored by the close
handler for 700 ms.

## Tests

Frontend **30 passing** (29 + 1): every step's timing is within the floor and ceiling, and
a longer step is given longer. Backend untouched; 308 passing.

Checked in a real browser at 1366×640: a tap anywhere unmutes without closing, Skip still
closes, the tour advances by itself and pauses on the pause button and on manual Back and
Next, and every ring is on screen and on the right link including Models and Users.
