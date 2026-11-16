# AGRISCAN p11 — richer visual surface

Visual language taken from the reference: dark hero band, ring gauges, grouped
section cards with an eyebrow and a corner figure, more depth and radius.

## What changed

- **Hero band** on Overview. Deep field-green gradient, four ring gauges showing the
  pipeline: images captured, model detections, awaiting review, technician verified.
- **Section cards** replace flat panels. Each has a named group, a title, a one-line
  note and an optional figure in the corner.
- **New tokens**: `--leaf-bright` for gauge arcs, `--paddy-deep` and `--paddy-mid`
  for hero bands, `--radius-xl`, `--shadow-lift`.

## New: dataset readiness

The strongest addition, and it is real data rather than decoration.

One row per condition, showing verified samples against the 150-sample minimum from
Chapter 3, plus the field count and visit-date count. A class is marked trainable only
when it clears all three: 150 samples, 3 fields, 2 dates. Anything short says what is
missing — "47 more", "1 more field", "1 more date".

This figure decides which classes can be reported at all, and until now it lived only
inside `scripts/validate_split.py`, which nobody runs during collection. It is computed
in the browser from the verified detections, so it updates as the technician clears
the queue.

## What was deliberately not built

The reference carries 3D Terrain and Topographic Analysis, Water Body Analysis,
Fertilizer Compatibility Analysis, and Bayesian-Spatiotemporal Pest Outbreak Detection.

AGRISCAN has no elevation model, no soil data, no hydrological data and no outbreak
time series. Those pages could only be filled with invented numbers. The Track B
providers already return HARDWARE_REQUIRED or INSUFFICIENT_DATA for exactly these, and
they have no navigation entry for the same reason.

The ring component takes a numerator and a denominator, never a bare percentage,
specifically so a fabricated figure cannot reach a page that looks authoritative.

## Tests

Frontend 15 passing, build clean, 1682 modules. Backend untouched at 265.
