# AGRISCAN p21 — ready to deploy

Extract over p20. **Keep your `backend\.env`**; it is not in this package. Then:

```powershell
cd backend; .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m migrations.run_migrations     # 010_deployment.sql
cd ..\web; npm ci; npm run build
```

Deployment steps are in `DEPLOY.md`.

## Before going public: four things that were unsafe

| Problem | What would have happened | Now |
|---|---|---|
| `backend\.env` was inside the zip | DB password and secret key travel with every copy | Not in this package. Generate a new secret for the server |
| Demo accounts use `demo-password-change-me` | That password is in `seed.py`. On a public host anyone signs in as DEMO Admin | Preflight refuses a production start while any active demo account has it |
| Stub detector on a real server | Every farmer photo gets "Brown spot, 91.4%", stored as real data | The production worker refuses the stub. Photos queue until a model is registered |
| No sign-in limit | Unlimited password guessing against farmer accounts | 8 failures per name or 30 per address in 15 minutes, then 429 |

## Serving

`python serve.py` is the whole site on one port: the built React app at `/`, the API at
`/api`, exactly the shape the Vite proxy already gave the frontend. Waitress, because
gunicorn does not run on Windows.

- Deep links (`/field/results/12`, `/camera`) open the app on reload.
- Hashed assets cached for a year, `index.html` and `sw.js` never, so an update shows.
- A missing old chunk is a real 404, not `index.html`. Serving HTML where JavaScript is
  expected gives a MIME error instead of a reload.
- `.js` is served as JavaScript explicitly. Some Windows machines map `.js` to
  `text/plain` in the registry, which gives a blank page.
- Security headers: a content-security policy (scripts from this server only, map tiles
  the only outside source), no framing, camera and location allowed for this site only,
  HSTS in production over HTTPS. API responses are `no-store`.
- Every API request goes to `backend\logs\agriscan.log` with status and time.
- Preflight runs on every start: secret, database, migrations, web build, real admin,
  demo passwords. Production will not start with a `FAIL`.

## Things that were broken and nobody had hit yet

**File paths depended on the folder you started from.** `./data/images` resolved
against the current directory. A worker started from the project root looked for photos
in a different place than the website saved them. Now relative to `backend\`. Existing
rows are unchanged and still resolve.

**The worker reloaded YOLO weights for every photo.** Seconds per image once a real
model is on. Loaded once now.

**A crashed worker left jobs RUNNING forever.** Closing the window mid-photo meant that
photo never got a result. Stale jobs are put back after 10 minutes; one that crashes the
worker every time still ends as FAILED.

**The worker died when MySQL restarted.** It now waits and reconnects.

**Your dataset is a classification dataset; the pipeline only read boxes.** One folder
per condition trains YOLO26n-cls, which returns a score per class and no boxes. The
worker would have produced nothing. It now reads classification output, and severity is
reported as *not measured* rather than 0%, because there is no area to measure.

**Wrong password said "Your session has ended."** Every 401 was treated as an expired
session, including a mistyped password on the sign-in page.

**An expired session left the page looking signed in.** Every request failed with no way
forward. It now returns to sign-in and says why.

**The image list scanned the whole jobs table per image.** One flight is ~300 photos.
Migration 010 adds an indexed `jobs.image_id`.

**A bad date filter was a 500.** `?date_from=yesterday` is now a 400 with the reason.

**The required-field asterisk was never red.** `--danger` was used since p16 and never
defined.

## Accounts

- Everyone can change their own password: user chip on the dashboard, name at the top of
  the field client. Other devices are signed out; this one stays signed in.
- Admins on the Users page: change role, deactivate or reactivate, reset a password. You
  cannot demote or deactivate yourself.
- Deactivation and password changes take effect on the next request. Every token now
  carries a password version; a mismatch is refused.
- `python -m scripts.create_admin` makes the first real admin. The password is typed,
  never on the command line.

## Phone layout

The sidebar was 236 px at every width. On a phone, a technician arming the drone camera
in the field had about 140 px of page. Below 900 px it is now a drawer behind a menu
button. Above 900 px nothing changed.

## When something goes wrong

- **A page crash no longer blanks the app.** It shows what failed, a reload button, and
  *Copy details* with the exact error to send. The p19 crash would have produced this.
- **After an update, open tabs reload themselves once** onto the new version instead of
  failing to load a page that no longer exists.
- **Status banner for operators**, only when something needs doing: database down, photos
  waiting with nothing analysing them (and whether that is because no model is in
  production), or failures in the last 24 hours. `/api/health` now checks the database
  and the queue instead of always saying ok.

## Smaller

- Inter is bundled instead of loaded from Google Fonts. The laptop server may have no
  internet, and the field client must open with no signal.
- App icon, favicon and web manifest: farmers can add AGRISCAN to their home screen.
- Service worker v3 clears the v2 caches.
- Drone camera page gives the HTTPS address for a deployed server, not only the dev one.
- `web\.env.example` no longer suggests a `VITE_API_BASE` that would break every phone.
- `scripts\backup.ps1`, the Windows version of `backup.sh`.
- `scripts.register_model` copies weights, checks class names against the conditions,
  retires the previous production model. `scripts.import_conditions` adds the missing
  ones from a CSV.
- `HILIGAYNON-REVIEW.csv` has two new rows: *My account* and *Change password*.

## Not changed

The visual design. Colours, type, page structure and every p15–p20 decision are as they
were; new elements use the existing tokens.

## Tests

Backend **308 passing** (265 + 43 new) on a real MariaDB. Frontend 15 passing, build
clean. `serve.py` was run and checked in a real browser with the security policy on: no
blocked resources, sign-in, nine dashboard pages, creating an account, the phone drawer,
and a farmer changing their password.

New tests: `test_p21_accounts.py`, `test_p21_deployment.py`.
