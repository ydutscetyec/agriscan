# AGRISCAN p36 — images you can open, and the session fault closed

Extract over p35. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration. Reload `/camera` on the phone afterwards.

## Images open full size

Click any thumbnail in **Captured images** and the full picture opens over the page, with
its id, field, source and capture time. Escape or a click outside closes it.

An 84-pixel square cannot tell you whether a frame is sharp, level and actually of rice.
That is the whole reason to look at a capture.

## Why your sessions stopped — and what your diagnostics panel showed

Your screenshot was the first real evidence in six rounds, and two lines of it mattered:

- **"Already finished here: 26, 27, 28, 29, 30"** — the phone *did* receive every one of
  those sessions. They were never ignored.
- **"Stopped from the dashboard. 0 frames saved on this phone."** — each was ended by the
  server saying "idle" while the phone still held it.

So the phone picked each session up, captured nothing, and was then told the session no
longer existed. Meanwhile the dashboard said "the phone never picked this up", because
the only proof of pickup was a report that arrives on the *next* poll — and none ever
arrived.

**Fixed: the phone now reports the moment it starts.** Not three seconds later. Anything
that interrupts it in between — a reload, an expired sign-in, the page going to the
background — no longer erases the fact that the session was taken.

That matters because of what p35 fixed: the tour was navigating the phone off `/camera`.
A phone pulled off the station page mid-session is exactly a phone that starts a session,
captures nothing, comes back, and is told the session is over.

Verified in a browser driving a simulated phone, the dashboard route this time:
**armed from the dashboard → session running, 5 frames, phone reporting.** Combined with
p35's phone-started run (8 frames), both paths now work end to end.

## A visible session log on the phone

Under **Show connection details** there is now a short history: when a session started,
when it ended, and why. Eight entries, with times.

If anything goes wrong again, that is one screenshot instead of four rounds of guessing.
I should have added it before the diagnostics panel, not after.

## Where you actually are

You have 10 captured images on the server from the phone-started run. That is the first
real data the system has produced. The pipeline from phone to database works.

What still has never happened: a trained model, and therefore a single real detection.
The 43 Drive folders still do not match the 9 condition codes, and nothing downstream —
verification, recommendations, accuracy — has run on anything.

## Tests

Backend 367 passing, frontend 30 — unchanged; this release is frontend behaviour the unit
suites do not reach. The checks that mattered were the two browser runs described above,
plus the viewer: a card opens, the full image loads, Escape closes it.
