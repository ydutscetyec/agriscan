# AGRISCAN p29 — viewfinder: see what the drone phone sees

Extract over p28. **Keep your `backend\.env`.**

```powershell
cd web; npm ci; npm run build
```

No migration.

## What you get

On **Drone camera**, each paired phone now has a **Show camera** button. Press it and you
see what that phone's camera is pointing at, refreshed about every two seconds, with the
age of the picture always on screen.

Use it on the ground before takeoff to check the phone is aimed straight down, in focus,
and actually looking at rice. Use it in the air to confirm you are over the field you
think you are over.

## What it is not

It is not live video, and the page says so rather than letting you assume otherwise.

Live video from a phone to a laptop means WebRTC, a signalling server, and almost
certainly a TURN relay, because both ends sit behind carrier NAT. That is a second
service to keep alive during a flight, on top of the tunnel — and when the link stutters,
a stream loses that footage for good.

This sends one small JPEG instead: 480 px wide, low quality, about 20 kB, roughly
10 kB/s. It survives a bad connection, costs little data, and reuses the polling the
phone already does. Against the several megabytes of a real capture, a viewfinder frame
is noise.

## It only runs while you are watching

The phone does not send frames unless an operator has the viewfinder open. The dashboard
tells the server it is watching every time it pulls a frame; the server passes that on in
the phone's next poll; twelve seconds after you stop looking, the phone stops sending.

A flight nobody is watching costs no data at all. A test covers this directly, including
that watching one phone does not wake another.

The phone shows **"The dashboard is watching this camera"** while it is sending, so
whoever is holding it knows.

## Stale frames look stale

A viewfinder that quietly shows an old picture is worse than no viewfinder — an operator
would trust it while aiming at nothing. If a frame is more than eight seconds old, the
picture goes grey with a red outline and the caption reads *"Last frame 12s ago — the
phone has stopped sending."*

**This was wrong in my first version and the browser test caught it.** I was measuring
how long ago the dashboard *fetched*, not how old the *frame* was. The server serves the
same file happily forever, so a phone that died mid-flight would have gone on looking
live. The server now sends the frame's real age in a header and the page uses that.

## Where the frames go

Nowhere. They are not Image rows, are never analysed, never enter the dataset, and only
the newest one exists — each frame overwrites the last at
`backend\data\images\_preview\device-<id>.jpg`. The folder can be deleted at any time.

Operators only: a farmer account gets 403 on both pushing and viewing.

## Tests

Backend **331 passing** (322 + 9 new): a pushed frame comes back with no-store and an age
header, only the newest is kept, no frame yet is a 404 rather than an error, the phone is
only asked for frames while someone watches, watching one phone does not wake another,
oversized and empty frames are refused, farmers are blocked, and an unknown device is
rejected. Frontend 30.

Checked in a real browser: a pushed frame appears within two seconds, the caption reads
correctly while fresh, the frame is marked stale after the phone stops, and it recovers
when the phone resumes.

## Flying with it

Leave the viewfinder **closed** during a long flight unless you are using it. It is cheap,
but it is not free, and the phone's battery and data are both finite. Open it for the
pre-flight check, close it, and open it again if you want to confirm coverage mid-flight.
