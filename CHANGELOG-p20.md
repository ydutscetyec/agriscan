# AGRISCAN p20 — content pages and the farmer client

## The pages beside the sidebar

They were a bare `h1` and a line of grey text on a cream background. Eleven pages
share `PageHeader`, so changing that one component lifted all of them.

The header is now a white card with a green left rule, an icon tile, the group the
page belongs to, the title and the description. A page read on its own now says
where it sits in the system.

| Group | Pages |
|---|---|
| Monitoring | Detections, Map, Verification queue, Recommendations |
| Capture | Drone camera, Flight records, Upload images |
| Fields | Field boundaries, Manage fields, Farmers |
| Analysis | Analytics |
| Administration | Model registry |

The Verification queue had two bare `h1` tags and no shared header at all. It now
uses the same one.

`PageHeader` also takes an optional `meta` row for short facts the page already
knows. It is there for real counts, not decoration.

## Four name collisions

Importing icons by their obvious names broke the build four times: `Users`,
`Upload`, `Plane`, `Sprout` and `Boxes` are also the names those pages export.
Each is now aliased, for example `Users as UsersIcon`.

Worth noting because the build failure is immediate and obvious — but only if you
build. Pasting these edits without running `npm run build` would have given a blank
screen with a console error.

## Farmer client

The form was loose fields on a background with nothing saying they belonged
together, or in what order.

- **Three cards, numbered**: 1 Photo, 2 Where, 3 Send. The farmer is doing three
  things in sequence and nothing said so.
- Each card is white on the cream page with a soft lift, so the task has edges.
- Result rows carry the same status rule and severity chip as the dashboard, so the
  two interfaces now use one vocabulary.

## Tests

Backend 265 passing, frontend 15 passing, build clean.
