# AGRISCAN p8 — the aircraft page

## New page: /aircraft ("The aircraft", under Capture)

An interactive 3D model of the F450, built to real dimensions from the ordered parts.
Drag to turn it; tap any component for its spec and mounting note.

Three controls:

- **Exploded** — parts separate along the direction they actually come off during
  disassembly, so it doubles as an assembly order.
- **Spin** — propellers turn at their correct relative directions.
- **Motor directions** — arrows above each motor plus a numbered table.

### Why the motor-direction view is the point

A photograph cannot show which way a motor turns, and this is the single most common
way a first quadcopter build fails: get it wrong and the aircraft flips on its first
throttle-up. The numbering shown is **ArduPilot's Quad X layout**, which is not the same
as Betaflight's:

| Motor | Position | Turns |
|---|---|---|
| 1 | Front right | Counter-clockwise |
| 2 | Rear left | Counter-clockwise |
| 3 | Front left | Clockwise |
| 4 | Rear right | Clockwise |

Adjacent motors always oppose; diagonal pairs match.

### Dimensions are real, not artistic

450 mm motor-to-motor diagonal (verified: 450.0 mm in the model), 2212 motors at 27.5 mm
diameter, 1045 propellers at 254 mm, Pixhawk at 81.5 × 50 × 15.5 mm, 3S pack at
105 × 34 × 25 mm. A student holding the part can match it to what is on screen.

Front arms are red and rear arms white, as the F450 ships — that is the only orientation
cue available once the aircraft is more than a few metres away.

### What it is not on

Deliberately not on the Overview or Map. A spinning aircraft above the detection counts
is decoration, and a panel reads it that way. It sits under Capture, beside the drone
camera it carries.

## Content on the page

- Component list with specs and mounting notes, including the assembly warnings that
  matter: compass on a mast away from power wiring, ESC calibration as a set, PETG rather
  than PLA for the phone mount, land at 20 percent battery.
- Flight envelope: about 5 usable survey minutes per pack, roughly 0.6 ha, 4.3 mm per
  pixel at 20 m. Labelled as estimates, because nothing has flown yet.
- The ₱10,076 build cost, with borrowed items excluded and said so.

## Technical

- `three@0.169.0` added. The page is lazy-loaded, so three.js lands in its own 530 KB
  chunk and only downloads when someone opens /aircraft. The main bundle is unchanged.
- `web/src/three/drone.js` — geometry and part metadata, separate from the page.
- Falls back to a text message where WebGL is unavailable; the specifications still show.
- Geometry disposed on unmount.

## Tests

Frontend 15 passing. Build clean, 1681 modules. Backend untouched at 185.
