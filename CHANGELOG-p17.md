# AGRISCAN p17 — includes p15 and p16

Extract this over p14. It contains everything from p15, p16 and p17, so any
half-applied hand edits are superseded.

## From the reference mockups: what was taken

**Photo tips on the capture screen.** The single most valuable idea in them. Image
quality is the limiting factor on the whole dataset, and nothing was telling farmers
how to take a usable photo. Folded away in a `<details>` so it is there the first few
times and out of the way after.

The tips are tied to the real quality gate, not generic advice: fill the frame, tap
to focus, keep your shadow off the plant, one plant part per photo. It also says
plainly that blurred or dark photos are rejected before the model sees them.

**A gallery option.** `capture="environment"` opens the camera and nothing else, so a
farmer who had already photographed the crop had no way to send it. There is now a
second input without that attribute.

**Quick actions on Overview** — start a capture session, upload images, open the map.
All three routes already existed.

**The pipeline counts are now links.** Images to Upload, detections to Detections,
awaiting review to the verify queue.

**A character counter** on the note field, 200 max.

## What was deliberately not taken

| In the mockup | Why not |
|---|---|
| Illustrated farm backgrounds | Decorative, heavy, and the generic-dashboard look the brief rules out |
| Stock leaf photos beside each class | They would be fabricated exemplars. Those classes have 0 verified samples; a photo next to them implies data that does not exist |
| "What AGRISCAN Detects" with four categories | Does not match the ten real condition classes. Misleading |
| Weather in the top bar | No weather data source. It would be invented |
| "Powered by AI & Drones", "Smart Farming. Healthier Harvest." | Marketing on a research instrument |
| Sparkles around the camera and send button | Decoration |
| "0%" on readiness bars | Counts are better: 0 of 150 says what is missing, 0% does not |

The readiness panel keeps counts and the explicit blocker, which is what decides
whether a class can be reported at all.

## Also in this package

**p15** — the bilingual label component hardcoded a grey, measuring **1.03:1** on the
Send button. "Ipadala" was invisible to a Hiligaynon reader. The second language now
inherits the full colour and is told apart by weight. Shutter gained an icon, tabs
gained icons and a working active state, the hint under Send was no longer clipped.

**p16** — Sign out was the most prominent control on screen, now a quiet outline.
Disabled Send measured 1.88:1 and read as half-active, now grey at 5.34:1. Zone and
Note are marked optional with help text below the input. A slot shows where the photo
will go.

## Checks

- Every `Link` in Home.jsx verified against the real route table. `/verification` was
  wrong and would have been a dead link; the route is `/verify`.
- Backend 265 passing, frontend 15 passing, build clean at 1682 modules.

## Before extracting

Keep your `backend\.env`. It is not in this package. Copy it back after extracting.

Frontend only, so no migrations. Run `npm install` in `web`, then `npm run dev`.
