# AGRISCAN p15 — farmer client

## The worst contrast fault in the project

`Bi`, the bilingual label component, hardcoded `--muted` for the second language.
That grey was fine on a white form row and **invisible everywhere else**:

| Surface | Was | Now |
|---|---|---|
| Send button | **1.03:1** | 4.75:1 |
| Shutter button | 1.03:1 | 4.75:1 |
| Active tab | low | 5.2:1 |

1.03:1 means "Ipadala" was the same lightness as the button under it. A farmer
reading in Hiligaynon had no label at all.

The first fix was to dim the second language with opacity instead. That was still
wrong: even at 92 % it only reached 4.09:1 on the tinted active tab. The second
language now inherits the full colour and is told apart by **weight** — bold English,
regular Hiligaynon. Worst case across every surface it appears on is 4.75:1.

## Capture screen

- **Shutter was a 100 px empty green banner.** Now a 60 px button with a camera
  icon, and a rotate icon when retaking.
- **Send was enabled with no photo.** Disabled until there is one, with a line
  saying why.
- **The explanation under Send was clipped by the tab bar.** The scroll area now
  clears it.
- Send uses the shared `lg` and `block` button variants and the busy spinner
  instead of inline padding overrides.

## Tab bar

Two bilingual phrases side by side were too long to read at a glance, which is the
only way a tab bar is ever read. Each tab now has an icon, the English on one line
and the Hiligaynon under it, in a 64 px target.

The active state was never wired: `NavLink` needs a function for `className`, so
`.fc-tab.active` had no effect and neither tab ever highlighted.

## Layout

On a laptop the column was adrift in a wide window. Content is capped at 560 px and
centred. The header gradient now runs top to bottom; across a short wide bar it read
as a smear.

## Tests

Frontend 15 passing, build clean. Backend untouched.
