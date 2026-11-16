# AGRISCAN p33 — satellite map, and the phone says what it is doing

Extract over p32. **Keep your `backend\.env`.**

```powershell
cd backend
python -m migrations.run_migrations      # migration 013
cd ..\web
npm ci
npm run build
```

## The map: OpenStreetMap blocked you

Those 403 tiles are OSM refusing to serve. Their tile servers run on donated hardware for
OSM's own use, and their usage policy says anything else needs its own source. A research
app behind a shared tunnel hostname is the kind of traffic they cut off, and pointing at
the same servers with a different URL would only be waiting to break again.

**The map is now Esri World Imagery by default** — satellite, which is the better map for
this work anyway. A street map of rural Surallah is mostly blank; satellite shows paddies,
bunds and water, so a detection marker lands on something you can recognise. A
**Satellite / Streets** switch sits above the map, with Streets on a community OSM mirror
that does permit third-party use. Both carry their required attribution.

## The phone now reports what it thinks it is doing

Your session 16 had Test 1 online, camera ready, viewfinder working — and still expired
with nothing. The dashboard could not tell the difference between two very different
situations, and said the wrong one:

- the phone is not polling at all
- the phone is polling and ignoring the command

The phone now sends the session it believes it is running on every poll. The device card
says **"Phone reports: idle"** or **"capturing for session 16"**, and when it is online,
has polled since the session was armed, and is still not on it, the card says so plainly:

> This phone is online and polling, but says it is not running the session armed for it.
> Reload /camera on the phone — its own state is stale.

That is the sentence that would have saved you the last two days.

## And a fix for the most likely cause

The phone kept its own idea of the running session. If that went stale — a session that
ended server-side while the phone was briefly offline, for instance — the phone would
refuse every later session, because it believed it was already busy. It polled normally
the whole time, which is exactly what you saw.

The server is the authority now: if it commands a session the phone is not on, the phone
abandons what it thought it was doing and takes the new one.

**Reload `/camera` on the phone after installing this.** The stale state is held in that
page, and a reload clears it.

### Honest note on this one

I cannot prove this was your fault, because I cannot see your phone's stored state. It
fits every symptom and it is a real bug that I fixed. If a session still comes back empty
after a reload, the card will now tell you which of the two situations you are in, and
that tells us both where to look next.

## Tests

Backend **367 passing** (361 + 6 new): an idle phone reports idle, a capturing phone
reports its session, a phone that is online and says idle while a session is armed is
flagged, a phone on the wrong session is flagged too, nothing is flagged without a session
to ignore, and the poll still commands the session. Frontend 30.

A detail worth recording: the flag first failed to fire because MySQL `DATETIME` has no
sub-second precision, so a poll and an arm within the same second compared as "has not
polled yet" — which hid the warning in exactly the case it exists for.

Checked in a real browser: the base map switch shows Satellite selected, and a phone
polling as idle against an armed session produces the warning and the "Phone reports:
idle" line.
