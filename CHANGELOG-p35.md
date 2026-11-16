# AGRISCAN p35 — start the capture from the phone

Extract over p34. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration. Reload `/camera` on the phone afterwards.

## First: p34 did not contain what I said it did

The diagnostics panel I told you to look for was never in that build. I edit these files
by matching a block of text and replacing it; that match failed, the edit silently did
nothing, and I packaged and shipped it without checking the panel existed. You went
looking for a link that was not there.

Both panels in this release were inserted with an assertion that the match succeeded, and
I confirmed them in a running browser before packaging. I should have been doing that all
along.

## Start a capture from the phone

The phone's page now has **Start capturing now**, with a field, an interval and a
duration. Press it and capture begins immediately.

The dashboard way still works and is unchanged. The difference is what has to go right:
arming from the dashboard creates a session and then waits for the phone to notice it on
its next poll. That notification step is where your last six sessions died. Starting from
the phone removes it — the phone creates the session and begins in the same breath. There
is nothing left to be missed.

The dashboard still sees the session, the viewfinder, the frame count, and can still stop
it. Only the starting moved.

Verified end to end in a browser driving a simulated phone: paired, pressed the button,
and the session came back **running, 8 frames, phone reporting**. That is the first time
in this run of versions that a session has actually captured anything.

## The tour was hijacking /camera

Found while testing the above. Navigating to `/camera` landed on the Overview instead,
because the tour opens on sign-in and its first step navigates to `/`.

This is the thing you reported several versions ago — *"when I type /camera it directs me
to the overview"* — which I diagnosed correctly, said I would fix, and then did not. The
tour now never opens or navigates on `/camera`, the same exclusion the intro video has
had since p22.

If that was happening on your phone, it would take the phone off the station page
entirely, which looks precisely like a phone that will not pair.

## The connection details panel, this time actually present

At the bottom of the phone's page, **Show connection details** opens six lines: the
device id this phone polls as, when the server last replied, what the server last
commanded, what the phone thinks it is running, which sessions it considers finished, and
whether the camera is ready.

If the dashboard way still fails for you, that panel says which half is at fault in one
screenshot.

## Tests

Backend 367 passing, frontend 30 — unchanged, since this release is frontend behaviour
that the unit suites do not reach. The real check was the browser run described above,
which is also why this one took another round to get right.
