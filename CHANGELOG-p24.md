# AGRISCAN p24 — pointed tour, sound on by default

Extract over p23. Frontend only. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration.

## The tour now points at things

The panel is larger (440 px wide, bigger heading and body text) and it is anchored: each
step sits beside the control that opens the page it is describing, with an arrow pointing
at it and a green ring around it.

| Step | Points at |
|---|---|
| All 16 dashboard pages | that page's link in the sidebar |
| Your account | the account chip in the top bar |
| Take a photo, My results | that tab in the field client's tab bar |
| My account (farmer) | the name at the top of the field client |

**Why these anchors and not the page content.** In p23 I argued against a pointing tour
because anchors break silently when something is moved or renamed. That still holds for
cards and headings inside a page. It does not hold for navigation: a sidebar link is
matched by the route it points to (`.as-navlink[href="/map"]`), so it cannot be renamed
or restyled out of the tour's reach without the route itself changing — and if the route
changes, the tour's own navigation breaks loudly on the same step rather than quietly
pointing at the wrong thing. Two tests enforce it: every step must anchor to a navigation
element, and every anchor must point at that step's own path.

**When there is nothing to point at, it does not pretend.** On a phone the dashboard
sidebar is a closed drawer, so the panel falls back to the docked sheet at the bottom
with no arrow. The farmer's tab bar *is* on screen on a phone, so that tour stays
anchored throughout.

The arrow follows the control if it moves — a page finishing its load, the drawer
sliding open, a list growing. That is done with a frame loop rather than scroll and
resize listeners, because most of those movements fire no event at all; it only
re-renders when the rectangle actually changes, so it costs a few renders per step
rather than sixty a second.

### Bug found while testing

On a phone the first step still anchored itself, to a sidebar link sitting off the left
edge of the screen inside the closed drawer. A hidden drawer is still in the DOM with a
real width and height, so the "is it visible" check passed on the vertical test and
never looked sideways. It now checks both axes.

## Sound is on by default

The intro now tries to start with sound on every load, and the speaker button is only
used to turn it *off* — that choice is remembered, nothing else is.

What you will actually see, which is not entirely up to the code:

- **Desktop Chrome or Edge, after a few visits:** sound plays by itself. Chrome keeps a
  media engagement score per site and starts permitting unprompted audio once a site has
  enough history of actually being watched. Your laptop will cross that line quickly;
  a farmer's phone opening the site for the first time will not.
- **Phones, and Safari anywhere:** it starts muted, and the speaker button grows a
  **Tap for sound** label so the one press it needs is obvious. One tap, sound from there.
- **Thereafter in that session:** unmuted.

There is no way to do better from any website. Autoplay with audio is blocked by every
browser until the person has interacted with the page or the browser has decided the
site has earned it, and a page that tries anyway gets its `play()` rejected and freezes
on the first frame. The fallback here is instant and silent: refused sound means it
plays muted immediately, never a still image.

If you want it silent by default again, set `SOUND_BY_DEFAULT = false` in
`src/components/Splash.jsx`.

## Tests

Frontend **29 passing** (27 + 2). New: every tour step anchors to a navigation control
and not to page content, and each anchor points at that step's own path. Changed: sound
is wanted by default, unreadable storage is not mistaken for "they turned it off".

Backend untouched; 308 passing.

Checked in a real browser: all 16 desktop steps anchor and ring their sidebar link with
no panel landing off screen, the phone dashboard tour falls back to the docked sheet, the
farmer tour stays anchored on a phone with the panel clear of the tab bar, the page never
scrolls sideways, and the splash shows **Tap for sound** when the browser refuses audio.
