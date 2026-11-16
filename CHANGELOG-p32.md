# AGRISCAN p32 — the ghost phone

Extract over p31. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration.

## What was actually wrong with your sessions

Your phone was paired, polling, camera ready, viewfinder working. Everything looked
right, and the sessions still expired with nothing.

**Pairing a phone creates a device row, and pairing it again creates another one.** The
phone only ever polls as the most recent pairing. You had Test 1, Test 2 and Drone
phone 1 — three rows, one physical phone. The sessions were armed at Test 1 while the
phone was polling as something else.

Nothing in the system was broken. The server armed a session at a device nobody was
listening on, and waited it out. The dashboard showed the old pairing in the dropdown
looking exactly as real as the live one, and let you arm it with no warning. That is the
fault, and it is mine.

## Three fixes

**Arming an unreachable phone is now refused** rather than silently wasting the flight.
If the chosen phone has not polled in the last minute, the server says so and says what
to do:

> 'Test 1' was last seen 10 min ago, so it would not pick this session up. Open /camera
> on the phone, then arm the device that shows as online. If this is an old pairing of a
> phone you have re-paired, delete it.

A brief stutter does not block anything — a phone polls every few seconds, so the
threshold is a minute. A phone that starts polling again becomes armable immediately.

**The dropdown now says which is which.** Every phone is listed with its state: *Test 2 ·
online*, *Test 1 · last seen 10 min ago*, *Drone phone 1 · never connected*. And a phone
that is actually polling is preselected, so the obvious choice is also the right one.

**Old pairings can be removed.** Offline device cards get a **Remove this pairing**
button for admins. The flights that pairing made are kept — deleting it does not rewrite
the record of what was flown — and the phone can pair again whenever it likes.

## What to do with your current state

1. Install this and rebuild.
2. Open Drone camera and look at the device cards. One will be online; the rest are
   ghosts from earlier pairings.
3. Remove the ghosts.
4. Arm a session on the one that remains.

If it still produces nothing after that, the problem is somewhere I have not looked yet
and I want to know.

## Tests

Backend **361 passing** (352 + 9 new): a polling phone arms normally, a silent one is
refused with its name and the remedy in the message, a phone that never connected is
refused too, a 30-second gap does not block arming, polling makes a stale device armable
again, an old pairing can be removed, a device with a live session cannot be, only admins
can remove one, and removing a pairing keeps its flights. Frontend 30.

Checked in a real browser: arming a 10-minute-old pairing returns 409 with that message,
the dropdown labels each phone's state, the online one is preselected, and removing a
pairing takes it out of the list.
