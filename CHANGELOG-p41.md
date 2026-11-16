# AGRISCAN p41 — the video upload goes in pieces

Extract over p40. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration. Restart `serve.py`, reload `/camera`.

## The 502 was Cloudflare, not your server

Cloudflare's free tier refuses a single request body over **100 MB**. A ten-minute 1080p
clip is several hundred, so the whole-file upload never reached your laptop at all — the
tunnel rejected it and handed back a 502 before Flask saw a byte.

Nothing in the server was wrong, and raising a limit there would not have helped.

## The upload is now chunked

The phone sends the video in **4 MB pieces** and the server appends them in order, then
assembles the file when the last one lands. Three consequences, all of them wanted:

- No single request is anywhere near Cloudflare's limit.
- A dropped connection costs one piece, not the whole upload. Each piece is retried once
  before the upload gives up, because a phone on one bar drops the odd request and
  failing an entire flight's video for that is the wrong answer after a flight.
- The button shows real progress — **Uploading… 47%** — instead of appearing frozen for
  several minutes.

Pieces that arrive out of step are **refused**, not appended. A video assembled from
pieces in the wrong order plays as garbage, and a file that looks present but is ruined
is worse than a failed upload you can see. Starting again from the first piece discards
whatever was half-sent.

## Verified end to end

A full run in a real browser against the running server: a one-minute session captured
**30 frames**, finished by itself, and the **9.5 MB video uploaded in chunks** and
registered against the session.

That is the whole path working for the first time: pair, capture, finish, upload stills,
upload video.

## Tests

Backend **391 passing** (383 + 8 new): pieces reassemble in order into the exact original
bytes, a piece out of step is refused with a message telling you to restart, restarting
discards the failed attempt, completing with nothing uploaded is refused, an unsupported
container is refused at completion, a second video cannot overwrite the first, the
session reports the video afterwards, and farmers cannot upload pieces. Frontend 30.
Suite run under `Asia/Manila` as well as UTC.

## Worth knowing for a real flight

A ten-minute clip is 100–150 MB and will take a while over mobile data. Upload it on
Wi-Fi when you can. The clip stays on the phone until it is sent, survives a reload, and
is offered again next time you open `/camera` — so there is no hurry and nothing is lost
by waiting until you are home.
