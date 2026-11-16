# AGRISCAN p37 — one bad photo no longer kills the worker

Extract over p36. **Keep your `backend\.env`.**

```powershell
cd backend
python -m scripts.seed          # adds the missing aerial placeholder
cd ..\web
npm ci
npm run build
```

No migration.

## What stopped your worker after two seconds

Image 3 came from the drone, so it needs a model registered for **aerial**. Your database
had only a **ground** placeholder, because the seed script only ever created one. The
worker hit that on its first job and exited.

Two faults, both mine:

**The seed only registered one mode.** It now registers a placeholder for each, so a
drone photo and a phone photo both have a row to point at. Re-run `python -m scripts.seed`
— it is safe to run again and will only add what is missing.

**One unprocessable photo stopped everything.** That is the worse of the two. A single
drone image with no aerial model took down the entire worker, so every queued phone photo
stopped being analysed as well, and the only sign was one line in a terminal you happened
to be watching.

Now a job whose mode has no model goes back on the queue untouched and the worker carries
on with everything else. The photo is not failed and its retry budget is not spent — it
is analysed the moment a model for its mode exists. The warning is logged once every five
minutes rather than twice a second.

The worker still refuses to start if there is no production model for **any** mode, which
is the case where it genuinely has nothing to do.

## Also

`.venv\Scripts\Activate.ps1` did not work because PowerShell needs the leading `.\`:

```powershell
.\.venv\Scripts\Activate.ps1
```

## What this does not fix

Both placeholder rows are `deployment_status='training'`, not production, and have no
weights behind them. With `AGRISCAN_DETECTOR_IMPL=stub` every analysed photo still gets
the same synthetic result, which is fine for testing the pipeline and must never be shown
to a farmer.

The queue will stay full until you register real trained weights. Nothing in this release
changes that, and it remains the only thing left between you and a result.

## Tests

Backend **371 passing** (367 + 4 new): a mode with no model raises an error that names the
mode, a drone photo with no aerial model leaves the worker running and the job queued,
repeated encounters do not exhaust the retry budget, and the job records which mode was
missing. Frontend 30.
