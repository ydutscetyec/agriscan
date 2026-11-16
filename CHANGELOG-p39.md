# AGRISCAN p39 — paired phones can actually be deleted

Extract over p38. **Keep your `backend\.env`.**

```powershell
cd web
npm ci
npm run build
```

No migration.

## Why removal did not work

Two reasons, and between them they covered every pairing you have.

**The button only appeared on offline cards.** So the phone you were actually holding —
the one connected and polling — was the single pairing you could never clear. The reason
I hid it was to stop someone unpairing a phone mid-flight, which is a real concern, but
it made the feature useless in exactly the case you kept hitting.

**And a device with a session still armed was refused.** The server said no, correctly,
but with a message that went nowhere you would look. Most of your ghost pairings have a
session stuck against them from the days when the timezone bug was expiring everything,
so most of them refused silently.

## Now

**Remove this pairing** is on every device card for admins, online or not. Pressing it:

- warns you if the phone is online, and that it will need to pair again
- names the session that is still running, and stops it for you as part of removing
- shows the actual error if anything else goes wrong, instead of doing nothing

Flights the pairing already made are kept. Deleting a pairing does not rewrite the record
of what was flown.

Verified in a browser: ten pairings, three removed in a row — including a connected one
and one with a live session — with no errors.

## Suggested clean-up

You have accumulated Test, Test 1, Test 2, Testt, pls, Please and Drone phone 1 for one
physical phone. Remove all of them, then pair once with a name you will recognise, and
arm from that. Every one of those rows is a way to start a session that goes nowhere.

## Tests

Backend **378 passing** (376 + 2 new): an online pairing can be removed, and the refusal
when a session is in the way names both the session and the phone. Frontend 30. Suite run
under `Asia/Manila` as well as UTC.
