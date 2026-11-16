# AGRISCAN p14 — one control system, and three contrast faults fixed

Every input, select, date picker, checkbox, file picker and button now follows one
set of rules: 40 px tall, white background, same radius, same focus ring.

## Three faults found by measuring

These were already in the app. I found them by checking contrast rather than looking
at the screen, which is the only way these show up.

| Fault | Was | Now |
|---|---|---|
| **White on the primary button** | `#8BAF3F`, **2.53:1** — well under AA | `#587A29`, 4.96:1 |
| Input placeholder | `#9AA0A6`, 2.64:1 | `#6E747B`, 4.72:1 |
| Input border | `#E2E0DA`, 1.32:1 | `#8E9489`, 3.11:1 |

The button one matters most. The page background is warm white and inputs are white,
so **the border is the only thing marking where a field begins** — at 1.32:1 it was
nearly invisible. WCAG asks 3:1 for a control boundary.

`--green` is unchanged for arcs, rules and tints. Only surfaces carrying white text
moved to `--green-btn`. Dark green on the light-green tint also measured 3.51:1, so
chips, pills and active tabs now use `#537426`.

## Controls

- **Inputs were grey**, which reads as disabled — visible on the sign-in page where
  both fields looked switched off. They are white now; grey means actually disabled.
- **Selects** get one chevron everywhere instead of each browser's own arrow.
- **Date fields** get a 20 px calendar button, tinted green, with a hover target.
  The native one is tiny and low contrast.
- **Checkboxes and radios** are branded with `accent-color`, which keeps the
  platform's own keyboard and screen-reader behaviour rather than reimplementing it.
  `.as-check` makes the label text a hit target too.
- **File inputs** get a styled picker button instead of the browser default.
- **Buttons** gain `sm`, `lg`, `block`, `danger`, `ghost`, and a `data-busy` spinner
  now wired into sign-in, upload, create account and start session.
- **Invalid state** via `aria-invalid`, paired with `.as-error` text so it never
  relies on colour alone.
- **Field client** controls are 52 px and 16 px type, checkboxes 22 px.

Reduced motion is respected: the spinner slows and the button press offset is removed.

## Tests

Frontend 15 passing, build clean. Backend untouched at 265.
