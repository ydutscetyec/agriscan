import * as THREE from 'three'

/*
 * The AGRISCAN aircraft, built to real dimensions from the ordered parts.
 *
 * Units are metres. Every figure below is the manufacturer's dimension for the part
 * actually bought, not an artistic approximation — the point of this model is that a
 * student holding the part can match it to what is on screen.
 *
 * Forward is -Z. Front arms are red and rear arms white, which is how an F450 ships
 * and the only orientation cue you get once the aircraft is more than a few metres away.
 */

// F450: 450 mm motor-to-motor diagonal, so each motor sits 225 mm from centre,
// at 45 degrees => 225 / sqrt(2) on each axis.
export const DIAGONAL_MM = 450
const R = 0.225 / Math.SQRT2 // 0.1591 m

const PROP_D = 0.254 // 1045 propeller: 10 inch diameter, 4.5 inch pitch
const PLATE_Y = 0 // bottom plate (power distribution board) sits at the origin
const TOP_Y = 0.039 // F450 plate separation

/* ArduPilot Quad X motor numbering and rotation. This differs from Betaflight's
   numbering, and getting it wrong flips the aircraft on its first throttle-up. */
export const MOTORS = [
  { id: 'm1', n: 1, x: +R, z: -R, spin: 'CCW', place: 'Front right', arm: 'front' },
  { id: 'm3', n: 3, x: -R, z: -R, spin: 'CW', place: 'Front left', arm: 'front' },
  { id: 'm2', n: 2, x: -R, z: +R, spin: 'CCW', place: 'Rear left', arm: 'rear' },
  { id: 'm4', n: 4, x: +R, z: +R, spin: 'CW', place: 'Rear right', arm: 'rear' },
]

/* Part metadata. `explode` is the direction a part moves in the exploded view, and is
   chosen to match how the part actually comes off during disassembly. */
export const PARTS = {
  frame: {
    name: 'F450 frame and arms',
    spec: '450 mm diagonal, glass-fibre plates, integrated power distribution',
    note: 'Red arms forward. The bottom plate is the power distribution board — the four ESC pairs solder directly to it, so check polarity before the first connection.',
    explode: [0, 0, 0],
  },
  fc: {
    name: 'Pixhawk PX4 2.4.8',
    spec: '81.5 × 50 × 15.5 mm, mounted on the top plate',
    note: 'Arrow points forward, along the red arms. Mount on vibration foam, not hard standoffs. This replaced the APM 2.8 because GPS waypoint flight is a project requirement.',
    explode: [0, 0.10, 0],
  },
  gps: {
    name: 'M8N GPS and compass',
    spec: '50 × 50 mm puck on a folding mast',
    note: 'Raised on a mast to clear the power wiring, whose magnetic field otherwise pulls the compass. Arrow forward, same as the flight controller.',
    explode: [0, 0.16, 0],
  },
  motors: {
    name: '2212 930KV motors',
    spec: '4 × brushless outrunner, 27.5 mm diameter',
    note: '930KV on 3S is the standard F450 pairing. Motors 1 and 2 turn counter-clockwise, 3 and 4 clockwise.',
    explode: [0, 0.07, 0],
  },
  props: {
    name: '1045 propellers',
    spec: '4 × 10 inch diameter, 4.5 inch pitch',
    note: 'The propeller must match its motor direction. Field check: the thicker leading edge leads into the turn, and every propeller pushes air downward. Confirm by hand before connecting the battery.',
    explode: [0, 0.13, 0],
  },
  esc: {
    name: '30 A ESCs',
    spec: '4 × 30 A, mounted along the arms',
    note: 'Swap any two of the three motor wires to reverse a motor. Calibrate all four together so they share one throttle range.',
    explode: [0, 0.03, 0],
  },
  battery: {
    name: 'ZOP 3S 2250 mAh 60C',
    spec: '11.1 V, XT60 connector, 3 packs carried',
    note: 'About five usable survey minutes per pack, roughly 0.6 ha. Land at 20 percent — taking a LiPo below 3.3 V per cell permanently damages it.',
    explode: [0, -0.13, 0],
  },
  power: {
    name: 'Power module',
    spec: 'Voltage and current sensing to the flight controller',
    note: 'Supplies the logged current draw used to work out real flight time, which is why no separate watt meter was bought.',
    explode: [0, -0.07, 0],
  },
  rx: {
    name: 'FlySky iA6B receiver',
    spec: '6 channel, PPM and i-BUS output',
    note: 'One three-wire lead to RC IN. The PPM encoder in the Pixhawk kit is not needed and stays in its bag.',
    explode: [0, 0.055, -0.06],
  },
  mount: {
    name: 'Phone mount',
    spec: 'PETG, vibration damped, camera pointing straight down',
    note: 'This is the AGRISCAN camera. Nadir orientation, damped so the rolling shutter does not smear at survey speed. PETG rather than PLA because a parked aircraft in Surallah sun softens PLA.',
    explode: [0, -0.20, 0],
  },
  gear: {
    name: 'Landing gear',
    spec: 'Approximately 110 mm, giving clearance for the phone',
    note: 'Take off and land from a dike or road. Propeller downwash at low altitude flattens standing rice, which would put false lodging into your own dataset.',
    explode: [0, -0.10, 0],
  },
}

const MAT = {
  plate: () => new THREE.MeshStandardMaterial({ color: 0x23272e, roughness: 0.62, metalness: 0.12 }),
  armFront: () => new THREE.MeshStandardMaterial({ color: 0xb2352a, roughness: 0.5 }),
  armRear: () => new THREE.MeshStandardMaterial({ color: 0xe8e6e0, roughness: 0.55 }),
  motorBell: () => new THREE.MeshStandardMaterial({ color: 0x8e949c, roughness: 0.32, metalness: 0.78 }),
  motorBase: () => new THREE.MeshStandardMaterial({ color: 0x33383f, roughness: 0.5, metalness: 0.4 }),
  prop: () => new THREE.MeshStandardMaterial({
    color: 0x1c1f24, roughness: 0.35, metalness: 0.1,
    transparent: true, opacity: 0.93, side: THREE.DoubleSide,
  }),
  board: () => new THREE.MeshStandardMaterial({ color: 0x2a6b46, roughness: 0.55 }),
  fcCase: () => new THREE.MeshStandardMaterial({ color: 0x1b1e24, roughness: 0.45 }),
  gps: () => new THREE.MeshStandardMaterial({ color: 0xf2f2ef, roughness: 0.5 }),
  battery: () => new THREE.MeshStandardMaterial({ color: 0x1a2b4a, roughness: 0.42 }),
  esc: () => new THREE.MeshStandardMaterial({ color: 0x14161a, roughness: 0.5 }),
  wire: () => new THREE.MeshStandardMaterial({ color: 0x0f1114, roughness: 0.7 }),
  mount: () => new THREE.MeshStandardMaterial({ color: 0x8BAF3F, roughness: 0.6 }),
  phone: () => new THREE.MeshStandardMaterial({ color: 0x0b0d10, roughness: 0.25, metalness: 0.5 }),
  glass: () => new THREE.MeshStandardMaterial({ color: 0x2a3240, roughness: 0.1, metalness: 0.6 }),
}

function tag(mesh, partId) {
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.userData.partId = partId
  return mesh
}

/** A propeller blade: planform outline extruded thin, then given pitch. */
function blade(material) {
  const hub = 0.013
  const tip = PROP_D / 2
  const s = new THREE.Shape()
  s.moveTo(hub, -0.010)
  s.bezierCurveTo(0.05, -0.016, 0.09, -0.014, tip, -0.004)
  s.lineTo(tip, 0.004)
  s.bezierCurveTo(0.09, 0.011, 0.05, 0.012, hub, 0.009)
  s.closePath()

  const g = new THREE.ExtrudeGeometry(s, { depth: 0.0016, bevelEnabled: false })
  g.translate(0, 0, -0.0008)
  const m = new THREE.Mesh(g, material)
  m.rotation.x = Math.PI / 2 // lie flat in the XZ plane
  m.rotation.z = 0
  const holder = new THREE.Group()
  holder.add(m)
  holder.rotation.z = THREE.MathUtils.degToRad(11) // blade pitch
  return holder
}

function propeller(spin) {
  const group = new THREE.Group()
  const mat = MAT.prop()
  const hub = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.013, 0.014, 0.008, 20), mat), 'props')
  group.add(hub)

  const a = blade(mat)
  const b = blade(mat)
  b.rotation.y = Math.PI
  // A propeller's blades sweep away from the leading edge, so mirror for the other spin.
  if (spin === 'CW') {
    a.scale.z = -1
    b.scale.z = -1
  }
  ;[a, b].forEach((holder) => {
    holder.traverse((o) => { if (o.isMesh) tag(o, 'props') })
    group.add(holder)
  })
  return group
}

function motorAssembly() {
  const g = new THREE.Group()
  const base = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0138, 0.0145, 0.012, 24), MAT.motorBase()), 'motors')
  base.position.y = 0.006
  const bell = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0138, 0.0138, 0.017, 24), MAT.motorBell()), 'motors')
  bell.position.y = 0.0205
  const shaft = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0017, 0.0017, 0.012, 10), MAT.motorBell()), 'motors')
  shaft.position.y = 0.033
  g.add(base, bell, shaft)
  return g
}

function roundedPlate(w, d, h, mat, partId) {
  const r = 0.008
  const s = new THREE.Shape()
  s.moveTo(-w / 2 + r, -d / 2)
  s.lineTo(w / 2 - r, -d / 2)
  s.quadraticCurveTo(w / 2, -d / 2, w / 2, -d / 2 + r)
  s.lineTo(w / 2, d / 2 - r)
  s.quadraticCurveTo(w / 2, d / 2, w / 2 - r, d / 2)
  s.lineTo(-w / 2 + r, d / 2)
  s.quadraticCurveTo(-w / 2, d / 2, -w / 2, d / 2 - r)
  s.lineTo(-w / 2, -d / 2 + r)
  s.quadraticCurveTo(-w / 2, -d / 2, -w / 2 + r, -d / 2)
  const g = new THREE.ExtrudeGeometry(s, { depth: h, bevelEnabled: false })
  g.rotateX(-Math.PI / 2)
  return tag(new THREE.Mesh(g, mat), partId)
}

/**
 * Build the aircraft.
 * Returns the root group plus handles the page needs: the four spinning propellers,
 * the per-part groups for exploding and highlighting, and the rotation markers.
 */
export function buildDrone() {
  const root = new THREE.Group()
  const groups = {}
  const spinners = []

  const get = (id) => {
    if (!groups[id]) {
      groups[id] = new THREE.Group()
      groups[id].userData.partId = id
      root.add(groups[id])
    }
    return groups[id]
  }

  // ---------------------------------------------------------------- frame
  const frame = get('frame')
  const bottom = roundedPlate(0.155, 0.155, 0.0025, MAT.board(), 'frame')
  bottom.position.y = PLATE_Y
  const top = roundedPlate(0.112, 0.112, 0.0018, MAT.plate(), 'frame')
  top.position.y = TOP_Y
  frame.add(bottom, top)

  for (const s of [-1, 1]) {
    for (const t of [-1, 1]) {
      const post = tag(new THREE.Mesh(
        new THREE.CylinderGeometry(0.0032, 0.0032, TOP_Y, 10), MAT.plate(),
      ), 'frame')
      post.position.set(s * 0.045, TOP_Y / 2, t * 0.045)
      frame.add(post)
    }
  }

  MOTORS.forEach((m) => {
    const armLen = Math.hypot(m.x, m.z) - 0.028
    const arm = tag(new THREE.Mesh(
      new THREE.BoxGeometry(armLen, 0.016, 0.025),
      m.arm === 'front' ? MAT.armFront() : MAT.armRear(),
    ), 'frame')
    const ang = Math.atan2(m.z, m.x)
    arm.position.set(
      Math.cos(ang) * (armLen / 2 + 0.028),
      0.0105,
      Math.sin(ang) * (armLen / 2 + 0.028),
    )
    arm.rotation.y = -ang
    frame.add(arm)

    const pad = tag(new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.005, 0.03), MAT.plate()), 'frame')
    pad.position.set(m.x, 0.019, m.z)
    frame.add(pad)
  })

  // ---------------------------------------------------------------- motors and props
  const motors = get('motors')
  const props = get('props')
  MOTORS.forEach((m) => {
    const mot = motorAssembly()
    mot.position.set(m.x, 0.0215, m.z)
    motors.add(mot)

    const p = propeller(m.spin)
    p.position.set(m.x, 0.0425, m.z)
    props.add(p)
    spinners.push({ mesh: p, dir: m.spin === 'CCW' ? 1 : -1 })
  })

  // ---------------------------------------------------------------- ESCs
  const esc = get('esc')
  MOTORS.forEach((m) => {
    const ang = Math.atan2(m.z, m.x)
    const e = tag(new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.010, 0.022), MAT.esc()), 'esc')
    e.position.set(Math.cos(ang) * 0.088, 0.0235, Math.sin(ang) * 0.088)
    e.rotation.y = -ang
    esc.add(e)
  })

  // ---------------------------------------------------------------- flight controller
  const fc = get('fc')
  const damper = tag(new THREE.Mesh(new THREE.BoxGeometry(0.070, 0.006, 0.046), MAT.wire()), 'fc')
  damper.position.y = TOP_Y + 0.0048
  const px = tag(new THREE.Mesh(new THREE.BoxGeometry(0.0815, 0.0155, 0.050), MAT.fcCase()), 'fc')
  px.position.y = TOP_Y + 0.0155
  const led = tag(new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.004, 0.012),
    new THREE.MeshStandardMaterial({ color: 0x8BAF3F, emissive: 0x4d6b1f, roughness: 0.4 })), 'fc')
  led.position.set(0.022, TOP_Y + 0.0238, 0)
  fc.add(damper, px, led)

  // ---------------------------------------------------------------- GPS on its mast
  const gps = get('gps')
  const mast = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.005, 0.098, 12), MAT.plate()), 'gps')
  mast.position.set(-0.028, TOP_Y + 0.049, 0.036)
  const puck = tag(new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.011, 0.05), MAT.gps()), 'gps')
  puck.position.set(-0.028, TOP_Y + 0.1035, 0.036)
  gps.add(mast, puck)

  // ---------------------------------------------------------------- receiver
  const rx = get('rx')
  const rxBody = tag(new THREE.Mesh(new THREE.BoxGeometry(0.047, 0.012, 0.024), MAT.esc()), 'rx')
  rxBody.position.set(0.0, TOP_Y + 0.0075, -0.046)
  rx.add(rxBody)
  for (const s of [-1, 1]) {
    const ant = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0011, 0.0011, 0.05, 6), MAT.wire()), 'rx')
    ant.position.set(s * 0.02, TOP_Y + 0.016, -0.066)
    ant.rotation.set(THREE.MathUtils.degToRad(-35), 0, THREE.MathUtils.degToRad(s * 22))
    rx.add(ant)
  }

  // ---------------------------------------------------------------- power module
  const power = get('power')
  const pm = tag(new THREE.Mesh(new THREE.BoxGeometry(0.036, 0.012, 0.020), MAT.esc()), 'power')
  pm.position.set(0.042, -0.0085, -0.030)
  power.add(pm)

  // ---------------------------------------------------------------- battery
  const battery = get('battery')
  const pack = tag(new THREE.Mesh(new THREE.BoxGeometry(0.105, 0.025, 0.034), MAT.battery()), 'battery')
  pack.position.set(0, -0.019, 0)
  const strap = tag(new THREE.Mesh(new THREE.BoxGeometry(0.022, 0.030, 0.038), MAT.wire()), 'battery')
  strap.position.set(-0.02, -0.018, 0)
  battery.add(pack, strap)

  // ---------------------------------------------------------------- phone mount
  const mount = get('mount')
  const cradle = tag(new THREE.Mesh(new THREE.BoxGeometry(0.086, 0.006, 0.058), MAT.mount()), 'mount')
  cradle.position.set(0, -0.070, 0.006)
  for (const s of [-1, 1]) {
    const post = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0035, 0.038, 10), MAT.mount()), 'mount')
    post.position.set(s * 0.034, -0.0475, 0.006)
    mount.add(post)
    const damp = tag(new THREE.Mesh(new THREE.SphereGeometry(0.006, 12, 10), MAT.wire()), 'mount')
    damp.position.set(s * 0.034, -0.030, 0.006)
    mount.add(damp)
  }
  const phone = tag(new THREE.Mesh(new THREE.BoxGeometry(0.076, 0.008, 0.156), MAT.phone()), 'mount')
  phone.position.set(0, -0.077, 0.006)
  const lens = tag(new THREE.Mesh(new THREE.CylinderGeometry(0.0085, 0.0085, 0.003, 18), MAT.glass()), 'mount')
  lens.position.set(0.021, -0.0825, -0.052)
  mount.add(cradle, phone, lens)

  // ---------------------------------------------------------------- landing gear
  const gear = get('gear')
  for (const s of [-1, 1]) {
    const skid = tag(new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.010, 0.190), MAT.plate()), 'gear')
    skid.position.set(s * 0.105, -0.112, 0)
    gear.add(skid)
    for (const t of [-1, 1]) {
      const leg = tag(new THREE.Mesh(new THREE.BoxGeometry(0.010, 0.112, 0.012), MAT.plate()), 'gear')
      leg.position.set(s * 0.078, -0.056, t * 0.062)
      leg.rotation.z = THREE.MathUtils.degToRad(s * -14)
      gear.add(leg)
    }
  }

  // ---------------------------------------------------------------- rotation markers
  const markers = new THREE.Group()
  markers.visible = false
  MOTORS.forEach((m) => {
    const colour = m.spin === 'CCW' ? 0x5B8DBE : 0xC98A1E
    const curve = new THREE.EllipseCurve(0, 0, 0.088, 0.088, 0, Math.PI * 1.45, m.spin === 'CW')
    const pts = curve.getPoints(48).map((p) => new THREE.Vector3(p.x, 0, p.y))
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: colour }),
    )
    line.position.set(m.x, 0.078, m.z)
    markers.add(line)

    const end = pts[pts.length - 1]
    const head = new THREE.Mesh(
      new THREE.ConeGeometry(0.010, 0.026, 12),
      new THREE.MeshBasicMaterial({ color: colour }),
    )
    head.position.set(m.x + end.x, 0.078, m.z + end.z)
    const tangent = new THREE.Vector3(-end.z, 0, end.x).normalize()
    if (m.spin === 'CW') tangent.negate()
    head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent)
    markers.add(head)
  })
  root.add(markers)

  return { root, groups, spinners, markers }
}

/** Free every geometry and material the model created. */
export function disposeDrone(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose()
    if (o.material) {
      if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose())
      else o.material.dispose()
    }
  })
}
