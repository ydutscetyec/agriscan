# AGRISCAN p40 — video that survives a crash, and flights you can download

Extract over p39. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration on the server. The phone's own storage upgrades itself on first load; queued
captures are kept.

## The flight video is now a real backup

p31 recorded the flight but held the whole clip in the page's memory until the session
ended. A phone that crashed, ran flat, or was killed in the background mid-flight lost
every second of it.

Now the recording is written to the phone's own storage **every ten seconds while it
records**. A crash costs at most the last ten seconds. When you reopen `/camera`,
anything still on the phone is offered for upload again rather than quietly kept.

**One change matters more than it looks:** recording is now WebM rather than MP4. A
recorder set to MP4 hands over nothing at all until it is stopped, so the periodic
backup had nothing to save — which I only found by checking the phone's storage
mid-flight instead of trusting the code. WebM delivers a chunk a second.

Measured in a running browser: 20 seconds into a session, **2.7 MB already on the phone**,
with the session still going.

## Disconnecting mid-flight

This already worked and is worth stating plainly, because it is easy to assume otherwise:

- Capture **keeps going** with no signal. The phone has the session and its own timer.
- Frames queue on the phone and upload when signal returns.
- The video is on the phone, not streamed, so it is unaffected.
- The viewfinder goes stale and says so. That is the only thing you lose.

When the phone reconnects after the server has already expired the session, it is told
the session is over and stops — correctly. The queued frames and the video still upload.

## Photos compiled by flight

**Captured images** is now grouped by the session that produced them, with a count per
group, instead of one flat list with drone and phone photos mixed together. Each group
has **Download all**: one zip of that flight's photos, named by capture order and time,
with a README recording the session, the field, the interval and how many files are in
the archive.

The zip is assembled on disk, not in memory. A ten-minute flight is a few hundred
full-resolution captures, and building that in RAM is how a laptop server falls over in
the middle of a defence.

## Tests

Backend **383 passing** (378 + 5 new): a session downloads as one archive with ordered
filenames and real JPEG content, the README explains itself, an empty session returns a
404 rather than an empty file, farmers are refused, and an unknown session is a 404.
Frontend 30. Suite run under `Asia/Manila` as well as UTC.

Verified in a browser: a capture running with 12 frames and the video already backed up
to the phone while it ran.
