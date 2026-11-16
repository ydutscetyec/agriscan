# AGRISCAN p31 — flight video, kept beside the stills

Extract over p30. **Keep your `backend\.env`.**

```powershell
cd backend
python -m migrations.run_migrations      # migration 012
cd ..\web
npm ci
npm run build
```

## What it does

The phone now **records the whole flight on video while it takes the stills**. Both at
once, not one instead of the other.

- **On the phone:** recording starts when a session starts and stops when it ends. The
  clip stays on the phone. When the session finishes, a panel offers **Upload flight
  video** with its size — send it on Wi-Fi if you can, because a 10-minute 1080p clip is
  100–150 MB. Discard is right next to it.
- **On the dashboard:** every session with a video gets a **Video** button in the
  Sessions table. It plays, it scrubs, and **Save this frame** pulls whatever you are
  looking at into Captured images.
- **A 1 Hz position track** is recorded alongside the video and uploaded when the session
  ends, whether or not you send the video. That is what gives a saved frame a position.

## Why the stills stay the detection source

This is the part worth being clear about, because it affects your paper.

Your phone shoots roughly 12 MP stills and records about 2 MP of video — a sixth of the
pixels, plus inter-frame compression that smears exactly the fine texture a disease
classifier reads. At 10–20 m nadir a lesion is already only a few pixels across.

And video has no per-frame GPS. A frame's position has to be interpolated from the track,
which is an inference rather than a record. Your Chapter 3 says geotagging uses phone
EXIF as the source of record; that stays true for the stills and cannot be true for video.

So a frame saved from video is marked twice over, in the database and on screen:

- `gps_source` is **`video_interpolated`**, a distinct value so any query can exclude it
- `from_video_offset_s` records where in the clip it came from

The warning sits above the Save button, not in a tooltip, because the person needs it
before they press rather than after. Saved frames are still queued for analysis like any
image — they are just never silently counted as ground truth.

## What the video is good for

Continuous coverage with no gaps between intervals; going back to a spot the interval
missed; and a record of the flight you can show someone. That is worth having, and it
costs the stills nothing.

## Bug caught while building it

The video and track uploaded fine and then read back as nothing. I had stored their paths
relative to the image folder's parent, while `resolve_stored()` resolves relative to
`backend\`, so every round trip pointed at a file that was not there. There is a
`stored_ref()` helper now, so media paths are written in the same form as
`images.file_path` and cannot drift apart again.

## Tests

Backend **352 passing** (340 + 12 new): the video round-trips, a second upload will not
silently replace the first, unsupported containers and empty files are refused, the track
round-trips, a frame between two fixes gets the interpolated midpoint, a frame outside the
track takes the nearest fix, a frame with no track gets no position rather than a guess,
the same frame twice is one image, a video frame is queued for analysis, and farmers are
blocked from both. Frontend 30.

Checked in a real browser, end to end: a genuine WebM recorded in the page, uploaded
with a track, played back, scrubbed to 1.5 s, and a frame saved — which came back as
*"Saved as image #6, position interpolated from the flight track"* and appeared in
Captured images.

## Still open

None of this moves the model. No trained weights are registered, nothing has run through
inference end to end, and the 43 Drive folders still do not match the 9 condition codes.
That remains the only thing standing between you and a result.
