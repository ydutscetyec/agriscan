# AGRISCAN p18 — the three outstanding items

## 1. Status and severity were never contrast-checked. Most of them failed.

Measured as text on white:

| Label | Was | Verdict |
|---|---|---|
| **Mild** | #A9C46C, **1.94:1** | unreadable |
| Not measured | #9AA0A6, 2.64:1 | fail |
| Low confidence | #9AA0A6, 2.64:1 | fail |
| Moderate | #C98A1E, 2.94:1 | fail |
| None | #648B2F, 3.98:1 | fail |
| Farmer confirmed / Technician verified | #648B2F, 3.98:1 | fail |
| AI detected, Rejected, Severe | 4.83 to 5.90 | pass |

Nine of twelve failed. **Severity is the field a farmer reads to know how bad it
is**, and four of its five values were below the minimum. "Mild" at 1.94:1 is pale
yellow-green on white.

### Why darkening alone was wrong

Darkening each colour to 4.5:1 while keeping its hue turned Mild into #677E33 and
None into #5D812C — two greens almost nobody could tell apart. Meeting contrast
would have destroyed the scale.

### What was done instead

Severity is now a chip: the hue sits in the background, the text is dark enough to
read against it, and the chip gets darker as severity rises, so the scale is legible
without colour vision at all.

| Severity | Chip | Text | Ratio |
|---|---|---|---|
| None | #EDF4E3 | #41601E | 6.39 |
| Mild | #F2F0CE | #5E6015 | 5.74 |
| Moderate | #F8E0BE | #8A5A0E | 4.62 |
| Severe | #F2D2CD | #8F2E23 | 5.76 |
| Not measured | #ECEDEF | #565C62 | 5.78 |

Status labels use darkened text variants. The marker shapes keep their original
strokes, which only have to clear 3:1 as non-text components — except Low
confidence at 2.64, now #8E959B at 3.03. That one mattered: it is the status most
needing to be noticed on the map.

Every severity still carries its word, so colour is never the only channel.

## 2. Map, Analytics and the Verification Queue

Moved onto the Section card used by Overview, so the three remaining plain pages
match the rest.

## 3. Hiligaynon

I cannot verify these. Every string is mine, and confident-sounding translation is
exactly the thing not to trust.

`HILIGAYNON-REVIEW.csv` in the project root lists all 20 strings with the English
beside them and two blank columns: Correction, and OK as is. Print it, give it to a
first-language speaker, type the corrections back into `src/field/labels.jsx`.

Worth asking about specifically: "Bahin sang uma" for Zone, and "Kasiguro sang
modelo" for how sure the model is. Both are my constructions rather than phrases I
have heard used.

## Tests

Backend 265 passing, frontend 15 passing, build clean.
