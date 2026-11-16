# AGRISCAN p13 — visible gradient, sign-in page, farmer and technician views

## The gradient was there, just invisible

p12 ran `#1B2520` to `#2C3A31`. Measured end to end that is a **1.32x** luminance
difference, which the eye reads as flat. It now runs `#141F18` to `#44633F`, a
**2.50x** difference, so the shift is visible down the left edge.

Opening the range meant the light end got much lighter, so the sidebar text had to
come up with it or fall below AA:

| Element | p12 | p13 |
|---|---|---|
| Nav link | `#C7D2C2` | `#E4EADF` |
| Group label, icons, brand sub | `#9AAD92` / `#A3B59B` | `#CFDBC9` |
| Lime accent | `#A8CC4A` | `#B4D96A` |

Every colour was re-measured against `#44633F`, the lightest point. All pass.

The Overview hero now uses its own darker pair (`--paddy-hero`) so two gradients do
not compete for attention on the same screen.

## Sign-in page

**The title was invisible.** It borrowed `.as-brand-name`, which p12 turned white for
the dark sidebar, so "AGRISCAN" was white on cream. Visible in the screenshot as a
ghost. The page now uses its own class names and cannot inherit that again.

Rebuilt as a split layout: a gradient panel carrying the brand mark, a line about what
the system does and who built it, beside a white form panel. Collapses to a single
column under 860 px, where the panel becomes a short band.

No demo credentials printed on the page. Those belong in the handover notes, not on a
public sign-in screen.

## Farmer view, the field client

Same identity, built for one thumb in daylight:

- Gradient header matching the sidebar, white brand and user line
- Offline pill now solid amber on dark text, 10:1, so it is readable in sun and does
  not rely on colour alone
- Tabs 60 px tall with a 3 px active rule
- The six answers get uppercase labels and 22 px values
- Result rows become cards with a status rule, matching the dashboard vocabulary
- Shutter button 64 px with a lift shadow

## Technician view

Uses the dashboard, so it picks up the sidebar, hero, section cards and the Detections
quick filters from p10 and p11.

## Tests

Frontend 15 passing, build clean. Backend untouched at 265.

## Not fixed

The 500 on Overview. Still needs the traceback from the backend window. The rings read
zero because of it, and the page says so rather than going blank.
