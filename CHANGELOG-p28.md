# AGRISCAN p28 — the fixes from the review

Extract over p27. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration. Thumbnails are generated on demand into `backend\data\images\_thumbs\`;
nothing to run, and the folder can be deleted safely at any time.

This covers items 2, 3, 4 and 6 from the review, plus the honest part of 5. Items 1, 7
and 8 are still open and are listed at the end.

## 2. "Internal server error" when the schema is behind

Two changes, because it failed in two places.

`python run.py` now checks the database before it serves and refuses to start when a
migration is missing, naming the file and the command. It used to start happily and fail
at the first query.

And any query that hits an unknown column or table now returns **503 with "The database
schema is out of date… run: python -m migrations.run_migrations"** instead of a generic
500 with the real reason only in the terminal. That is the exact failure that cost you an
afternoon last week; it is now self-explaining wherever it happens.

## 3. The tour no longer fights you

It still opens on every sign-in and still plays by itself. What changed: **the moment you
click or type anywhere outside the panel, it stops advancing.**

Before this, a technician signing in to clear the verification queue was navigated away
from it every twelve seconds for three minutes, and had to find Skip before they could
work. Now the tour stays on screen, paused, with its play button — so it is still there
if you were watching it, and out of the way if you were not.

## 4. Captured images was going to fall over on your first real flight

Two separate problems, both fixed.

**It downloaded the full-size photo for every row.** To draw an 84-pixel square. One
flight is about 300 photos at a few megabytes each, so the page pulled close to a
gigabyte to render a grid. There is now a `/images/<id>/thumb` endpoint that makes a
320 px JPEG once, caches it on disk, and serves it with the same ownership check as the
original. Measured in the test suite: the thumbnail is smaller than the full file,
is reused rather than regenerated on a second request, and is deleted with its image.

Thumbnails are also only fetched for rows at or near the screen, so the first screen
loads at the same speed whether there are ten photos or ten thousand.

**And the listing ran a query per row, several times over** — field, detections and job
per image, then the condition, model version and processing version of each detection on
top. Measured on a 50-image page: **153 queries before, 9 after.** It is now a fixed
handful for the whole page whatever the row count, with a test that fails if that
regresses.

Worth recording why the first attempt did not work: warming SQLAlchemy's identity map
with the related rows and letting `session.get()` find them there changed nothing —
it still issued a SELECT per row. The fix passes explicit lookup tables into the payload
builder instead. If you hit a similar N+1 elsewhere, do not assume the identity map will
save you; count the queries.

## 5 (partial). Truncation is now visible

The listing returns the true total, and the page says *"Showing the 50 most recent of
312"* when it is showing a slice. Full pagination is still not there — but silently
handing you a partial dataset with nothing on screen to say so was the dangerous half,
and that is gone.

## 6. `/health` no longer talks to strangers

It stays reachable without a token, because an uptime check has none — but without one it
now answers `{"status": "ok"}` and nothing else. Environment, build, detector, production
model names and queue depth are returned only to a signed-in admin, technician or
researcher. On a public tunnel those were free reconnaissance.

## Still open

- **1. No trained model has ever run.** Unchanged, and still the biggest risk to the
  research rather than to the website. The 43 Drive folders still do not match the 9
  condition codes.
- **7. `AppShell` rebuilds on every navigation.** A React Router layout route fixes it
  properly. It is a real refactor and I would not do it in the same package as four
  behaviour changes.
- **8. No end-to-end tests in the repo.** The browser testing I do each round lives in my
  sandbox, not in your project, so you cannot run it before a defence.

## Tests

Backend **322 passing** (314 + 8 new). Frontend 30.

New backend tests: the thumbnail is smaller than the original, is cached and reused, obeys
the same ownership rule, and is removed with its image; the listing's query count stays
under 15 for a 50-image page; the listing reports a total; a schema error returns 503 with
the migration command; `/health` without a token leaks nothing.

Checked in a real browser: clicking the page stops the tour advancing while leaving it on
screen, Captured images requests `/thumb` and never `/file`, and the unauthenticated
health response is `{"status":"ok"}` alone.
