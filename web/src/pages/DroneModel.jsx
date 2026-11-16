import { useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Box, Maximize2, RotateCw, Wind } from 'lucide-react'
import { MOTORS, PARTS, buildDrone, disposeDrone } from '../three/drone'
import { PageHeader } from '../components/Layout'

/*
 * The aircraft, as a build reference.
 *
 * This page exists to answer questions a photograph cannot: which way each motor turns,
 * where each component sits, and what order things come apart in. It is deliberately not
 * on the Overview — a spinning aircraft above the detection counts would be decoration.
 */

const ORDER = ['frame', 'motors', 'esc', 'props', 'fc', 'gps', 'rx', 'power', 'battery', 'mount', 'gear']

// Ordered from the ₱10,076 build sheet.
const COSTS = [
  ['F450 frame with landing gear', '987'],
  ['Pixhawk PX4 2.4.8 B set', '3,758'],
  ['2212 930KV motors, 30 A ESCs, 1045 props', '2,454'],
  ['3 × ZOP 3S 2250 mAh 60C', '2,277'],
  ['Spare propellers, 2 sets', '400'],
  ['LiPo charging bag', '200'],
]

export default function DroneModel() {
  const hostRef = useRef(null)
  const sceneRef = useRef(null)
  const [selected, setSelected] = useState(null)
  const [exploded, setExploded] = useState(false)
  const [spinning, setSpinning] = useState(false)
  const [showSpin, setShowSpin] = useState(false)
  const [ready, setReady] = useState(false)

  // Keep the render loop reading the latest toggles without rebuilding the scene.
  const state = useRef({ exploded: false, spinning: false })
  useEffect(() => { state.current = { exploded, spinning } }, [exploded, spinning])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return undefined

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x202532)

    const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 20)
    camera.position.set(0.40, 0.27, -0.44)

    let renderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    } catch {
      host.innerHTML = ''
      const msg = document.createElement('p')
      msg.className = 'as-muted'
      msg.style.padding = '24px'
      msg.textContent = 'This browser cannot display 3D graphics. The specifications below still apply.'
      host.appendChild(msg)
      return undefined
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    host.appendChild(renderer.domElement)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.touchAction = 'none'

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.target.set(0, -0.02, 0)
    controls.minDistance = 0.28
    controls.maxDistance = 1.4
    controls.maxPolarAngle = Math.PI * 0.86

    scene.add(new THREE.HemisphereLight(0xdfe6f0, 0x1a1d24, 1.05))
    const key = new THREE.DirectionalLight(0xffffff, 1.5)
    key.position.set(0.5, 0.9, -0.35)
    key.castShadow = true
    key.shadow.mapSize.set(1024, 1024)
    key.shadow.camera.near = 0.1
    key.shadow.camera.far = 3
    key.shadow.camera.left = -0.5
    key.shadow.camera.right = 0.5
    key.shadow.camera.top = 0.5
    key.shadow.camera.bottom = -0.5
    scene.add(key)
    const fill = new THREE.DirectionalLight(0x9fb8d8, 0.55)
    fill.position.set(-0.6, 0.3, 0.5)
    scene.add(fill)

    const { root, groups, spinners, markers } = buildDrone()
    root.position.y = 0.16
    scene.add(root)

    // A faint floor gives the shadow somewhere to land and the model a sense of scale.
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(0.6, 64),
      new THREE.ShadowMaterial({ opacity: 0.38 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.receiveShadow = true
    scene.add(floor)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.2249, 0.2261, 96),
      new THREE.MeshBasicMaterial({ color: 0x3a4152, side: THREE.DoubleSide }),
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.0005
    scene.add(ring)

    // Record each part's rest position so the exploded view can ease in and out.
    const rest = {}
    Object.entries(groups).forEach(([id, g]) => { rest[id] = g.position.clone() })

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    let downAt = null

    const onDown = (e) => { downAt = { x: e.clientX, y: e.clientY } }
    const onUp = (e) => {
      if (!downAt) return
      const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y)
      downAt = null
      if (moved > 6) return // a drag, not a click
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hits = raycaster.intersectObject(root, true)
      const hit = hits.find((h) => h.object.userData.partId)
      setSelected(hit ? hit.object.userData.partId : null)
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(host)

    let frame = 0
    let explodeAmount = 0
    const clock = new THREE.Clock()

    const tick = () => {
      frame = requestAnimationFrame(tick)
      const dt = Math.min(clock.getDelta(), 0.05)

      const target = state.current.exploded ? 1 : 0
      explodeAmount += (target - explodeAmount) * Math.min(1, dt * 6)
      Object.entries(groups).forEach(([id, g]) => {
        const e = PARTS[id]?.explode || [0, 0, 0]
        g.position.set(
          rest[id].x + e[0] * explodeAmount,
          rest[id].y + e[1] * explodeAmount,
          rest[id].z + e[2] * explodeAmount,
        )
      })

      if (state.current.spinning) {
        spinners.forEach((s) => { s.mesh.rotation.y += s.dir * dt * 26 })
      }

      controls.update()
      renderer.render(scene, camera)
    }
    tick()

    sceneRef.current = { groups, markers, root }
    setReady(true)

    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      controls.dispose()
      disposeDrone(scene)
      renderer.dispose()
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
      sceneRef.current = null
    }
  }, [])

  // Dim everything except the selected part, so the callout and the model agree.
  useEffect(() => {
    const s = sceneRef.current
    if (!s) return
    Object.entries(s.groups).forEach(([id, g]) => {
      const dim = selected !== null && selected !== id
      g.traverse((o) => {
        if (!o.isMesh) return
        const mats = Array.isArray(o.material) ? o.material : [o.material]
        mats.forEach((m) => {
          if (m.userData.baseOpacity === undefined) m.userData.baseOpacity = m.opacity
          m.transparent = dim || m.userData.baseOpacity < 1
          m.opacity = dim ? 0.11 : m.userData.baseOpacity
          m.depthWrite = !dim
        })
      })
    })
  }, [selected, ready])

  useEffect(() => {
    const s = sceneRef.current
    if (s) s.markers.visible = showSpin
  }, [showSpin, ready])

  const pick = useCallback((id) => setSelected((cur) => (cur === id ? null : id)), [])
  const part = selected ? PARTS[selected] : null

  return (
    <div className="as-content">
      <PageHeader
        title="The aircraft"
        description="An F450 quadcopter carrying a phone as its camera. Drag to turn it, tap any component to see what it is and how it mounts."
      />

      <div className="dm-layout">
        <div className="dm-stage">
          <div ref={hostRef} className="dm-canvas" />

          <div className="dm-controls">
            <button type="button" className={`dm-chip${exploded ? ' on' : ''}`}
                    aria-pressed={exploded} onClick={() => setExploded((v) => !v)}>
              <Box size={15} strokeWidth={1.9} /> Exploded
            </button>
            <button type="button" className={`dm-chip${spinning ? ' on' : ''}`}
                    aria-pressed={spinning} onClick={() => setSpinning((v) => !v)}>
              <Wind size={15} strokeWidth={1.9} /> Spin
            </button>
            <button type="button" className={`dm-chip${showSpin ? ' on' : ''}`}
                    aria-pressed={showSpin} onClick={() => setShowSpin((v) => !v)}>
              <RotateCw size={15} strokeWidth={1.9} /> Motor directions
            </button>
          </div>

          <div className="dm-scale">450 mm motor to motor</div>

          {part && (
            <div className="dm-callout" role="status">
              <div className="dm-callout-name">{part.name}</div>
              <div className="dm-callout-spec">{part.spec}</div>
              <p>{part.note}</p>
              <button type="button" className="as-btn secondary" onClick={() => setSelected(null)}>
                Show whole aircraft
              </button>
            </div>
          )}
        </div>

        <aside className="dm-parts" aria-label="Components">
          {ORDER.map((id) => (
            <button
              key={id}
              type="button"
              className={`dm-part${selected === id ? ' on' : ''}`}
              aria-pressed={selected === id}
              onClick={() => pick(id)}
            >
              <span className="dm-part-name">{PARTS[id].name}</span>
              <span className="dm-part-spec">{PARTS[id].spec}</span>
            </button>
          ))}
        </aside>
      </div>

      {showSpin && (
        <div className="as-note" style={{ marginTop: 16 }}>
          <strong>Get this wrong and the aircraft flips on its first throttle-up.</strong> The
          numbering below is ArduPilot's Quad X layout, which is not the same as Betaflight's.
          Adjacent motors always turn opposite ways; diagonal pairs match.
        </div>
      )}

      {showSpin && (
        <table className="as-table" style={{ marginTop: 12, maxWidth: 620 }}>
          <thead>
            <tr><th>Motor</th><th>Position</th><th>Turns</th><th>Arm</th></tr>
          </thead>
          <tbody>
            {[...MOTORS].sort((a, b) => a.n - b.n).map((m) => (
              <tr key={m.id}>
                <td style={{ fontWeight: 700 }}>{m.n}</td>
                <td>{m.place}</td>
                <td>
                  <span className="as-pill" style={{
                    background: m.spin === 'CCW' ? '#E8EFF7' : '#FBF3E2',
                    borderColor: m.spin === 'CCW' ? '#C3D5E8' : '#E6D6AE',
                    color: m.spin === 'CCW' ? '#2F5A85' : '#8A5A0B',
                  }}>
                    {m.spin === 'CCW' ? 'Counter-clockwise' : 'Clockwise'}
                  </span>
                </td>
                <td>{m.arm === 'front' ? 'Red, forward' : 'White, rear'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="as-grid cols-2" style={{ marginTop: 28, alignItems: 'start' }}>
        <section className="as-card plain">
          <h2>What one flight covers</h2>
          <p className="as-stat-filter" style={{ marginTop: 0 }}>
            Worked from the 2250 mAh pack and the phone's capture rate. Confirm against the
            flight log once the aircraft has flown.
          </p>
          <dl className="as-kv">
            <dt>Usable survey time</dt>
            <dd>About 5 minutes per pack, 15 minutes across three</dd>
            <dt>Area per pack</dt>
            <dd>Roughly 0.6 ha, so about one parcel</dd>
            <dt>Ground sample distance</dt>
            <dd>About 4.3 mm per pixel at 20 m</dd>
            <dt>Survey altitude</dt>
            <dd>30 m, raised from 20 m so the phone can keep up with the capture interval</dd>
          </dl>
          <div className="as-warn" style={{ marginTop: 12, marginBottom: 0 }}>
            These are estimates. Nothing here has flown yet.
          </div>
        </section>

        <section className="as-card plain">
          <h2>Build cost</h2>
          <table className="as-table">
            <tbody>
              {COSTS.map(([item, peso]) => (
                <tr key={item}>
                  <td>{item}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>₱{peso}</td>
                </tr>
              ))}
              <tr>
                <td style={{ fontWeight: 700 }}>Total</td>
                <td style={{ textAlign: 'right', fontWeight: 700 }}>₱10,076</td>
              </tr>
            </tbody>
          </table>
          <p className="as-stat-filter">
            The transmitter, receiver and charger are borrowed, so they are not counted here.
          </p>
        </section>
      </div>
    </div>
  )
}
