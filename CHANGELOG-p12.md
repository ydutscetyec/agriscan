# AGRISCAN p12 — gradient sidebar

The sidebar now carries the same deep field-green gradient as the hero band, so the
dark surface reads as one piece down the left edge.

| Element | Colour |
|---|---|
| Sidebar | `#1B2520` to `#2C3A31`, top to bottom |
| Nav link | `#C7D2C2` |
| Nav icon, brand sub | `#A3B59B` |
| Group label | `#9AAD92`, uppercase, tracked |
| Active link | white on a 14 % lime wash, bright lime left rule and icon |
| Focus ring | bright lime, inset |

## Contrast was checked, not assumed

Every colour was measured against the darkest point of the gradient, which is the
bottom. Two of my first choices failed there and were corrected:

| Element | First try | Now |
|---|---|---|
| Brand sub | `#8FA288`, 4.38:1 — below AA | `#A3B59B`, 5.49:1 |
| Group label | `#7E9177`, 3.53:1 — below AA | `#9AAD92`, 4.99:1 |

Nav links sit at 7.64:1, active text at 11.95:1. All small text now clears 4.5:1.

## The brand mark had to change

It was a dark navy tile with a near-white scan bracket, drawn for a white sidebar. On
a dark sidebar that tile disappears into the background. It is now a light tile
(`#E8EDE0`, 10:1 against the sidebar) with a dark bracket and one dark paddy square.

This also affects the drone camera station, which uses the same mark on a dark
background. It reads better there too.

## Tests

Frontend 15 passing, build clean. Backend untouched at 265.
