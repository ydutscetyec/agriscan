# AGRISCAN p38 — the timezone bug

Extract over p37. **Keep your `backend\.env`.** Backend only, no migration, no rebuild
needed — but restart `serve.py` and `worker.run`.

## This is the bug

Every stored timestamp in the database is **UTC**. The capture code compared those
timestamps against **local time**.

In Surallah your clock is UTC+8. So the moment a session was created, the server
calculated its age as **eight hours**, decided it was long past its one-minute limit,
expired it, and told the phone to stop. The phone obeyed and reported *"Stopped from the
dashboard"* — which is exactly what you have been seeing, every time, for days.

It explains every symptom at once:

- sessions ending "after a few seconds" regardless of the duration set
- "Duration limit reached without a completion report" on sessions a minute old
- 0 or 1 frames saved
- the phone insisting it was connected and ready, because it was

## Why I did not find it sooner

**My test container runs in UTC.** Local time and UTC are the same number there, so the
comparison was correct on every machine I ever ran the suite on, and wrong on yours. 371
tests passed while your phone could not complete a single capture.

I looked at the phone, the polling, the device pairing and the command handling —
everything that differed between us except the clock, which is the one thing I could not
see and should have suspected far earlier. A bug that reproduces only at a UTC offset is
exactly the kind that hides behind a green test suite, and I had no test that would have
caught it.

## The fix

One clock, in `app/utils/clock.py`, used everywhere. Seven places were calling
`datetime.now()` — capture expiry, image capture times, file paths, recommendation
approvals, risk timestamps and the health endpoint. All of them now use UTC.

And a test that fails without it. Reverting the fix and running under `Asia/Manila`
produces exactly your failure:

```
FAILED test_a_new_session_is_not_already_expired
FAILED test_the_phone_is_commanded_to_capture_rather_than_told_idle
```

With the fix, under the same timezone, all 376 pass.

## Run the tests at an offset from now on

```powershell
$env:TZ="Asia/Manila"; python -m pytest tests/
```

There is `scripts/run_tests_offset_tz.sh` for the same thing, and a note in the README.
Running the suite only in UTC is how this got through, and I would rather the project
makes that mistake impossible than rely on me remembering.

## What to expect after installing

Restart the server and the worker, reload `/camera`, and start a capture. A one-minute
session should now run for a minute and save frames the whole way through.

One existing oddity will persist: timestamps already written at local time are eight
hours out. Image capture times from earlier sessions may read wrongly. Nothing is lost
and nothing needs fixing — new rows are correct, and I would not rewrite history to tidy
it.

## Tests

Backend **376 passing** (371 + 5 new), under UTC *and* under `Asia/Manila`. Frontend 30.
