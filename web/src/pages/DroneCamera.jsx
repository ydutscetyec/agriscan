import { Link } from 'react-router-dom'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Camera, Play, Smartphone, Square, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import { EmptyState, PageHeader } from '../components/Layout'
import Viewfinder from '../components/Viewfinder'
import FlightVideo from '../components/FlightVideo'
import { useAuth } from '../state/auth'

/*
 * Start and stop capture sessions on a phone mounted on the drone.
 *
 * The phone does the timing itself. The dashboard only has to reach it twice: once on
 * the ground to start the session, and optionally again to stop it early. Everything
 * in between survives a dropped link.
 */

const REFRESH_MS = 3000

function secondsAgo(s) {
  if (s === null || s === undefined) return 'never'
  if (s < 60) return `${s} s ago`
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  return `${Math.round(s / 3600)} h ago`
}

const SESSION_PILL = {
  armed: ['warn', 'Waiting for phone'],
  running: ['ok', 'Capturing'],
  completed: ['idle', 'Completed'],
  stopped: ['idle', 'Stopped'],
  expired: ['warn', 'Expired'],
  failed: ['bad', 'Failed'],
}

function IntervalHelper({ onUse }) {
  const [altitude, setAltitude] = useState('30')
  const [speed, setSpeed] = useState('3')
  const [overlap, setOverlap] = useState('70')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const alt = Number(altitude)
    if (!alt) { setResult(null); return }
    api.plannerGsd(alt)
      .then((g) => {
        const spacing = g.footprint_height_m * (1 - Number(overlap) / 100)
        const interval = spacing / Number(speed)
        setResult({ gsd: g.gsd_mm_per_px, spacing, interval, camera: g.camera })
        setError(null)
      })
      .catch((err) => setError(err.message))
  }, [altitude, speed, overlap])

  return (
    <div className="as-card" style={{ marginBottom: 12 }}>
      <h3 style={{ marginBottom: 8 }}>Work out the interval</h3>
      <div className="as-grid cols-2" style={{ gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}>
        <div className="as-field">
          <label className="as-label" htmlFor="ih-alt">Altitude above crop (m)</label>
          <input id="ih-alt" type="number" min="5" max="60" className="as-input"
                 value={altitude} onChange={(e) => setAltitude(e.target.value)} />
        </div>
        <div className="as-field">
          <label className="as-label" htmlFor="ih-speed">Ground speed (m/s)</label>
          <input id="ih-speed" type="number" min="0.5" max="10" step="0.5" className="as-input"
                 value={speed} onChange={(e) => setSpeed(e.target.value)} />
        </div>
        <div className="as-field">
          <label className="as-label" htmlFor="ih-ov">Forward overlap (%)</label>
          <input id="ih-ov" type="number" min="50" max="90" step="5" className="as-input"
                 value={overlap} onChange={(e) => setOverlap(e.target.value)} />
        </div>
      </div>
      {error && <div className="as-warn">{error}</div>}
      {result && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13 }}>
            One frame every <strong>{result.interval.toFixed(1)} s</strong> gives a new frame each
            {' '}{result.spacing.toFixed(1)} m, at {result.gsd.toFixed(1)} mm per pixel.
            <div className="as-muted" style={{ fontSize: 12 }}>
              Estimated from camera settings labelled {result.camera}. Measure your actual
              phone before relying on it.
            </div>
          </div>
          <button type="button" className="as-btn secondary"
                  onClick={() => onUse(Math.max(0.3, Math.round(result.interval * 10) / 10))}>
            Use {Math.max(0.3, Math.round(result.interval * 10) / 10)} s
          </button>
        </div>
      )}
      {result && result.interval < 1.2 && (
        <div className="as-warn" style={{ marginTop: 8 }}>
          Under about 1.2 s most phones cannot keep up and will skip frames. Fly higher or slower.
        </div>
      )}
    </div>
  )
}

export default function DroneCamera() {
  const { can } = useAuth()
  const [devices, setDevices] = useState([])
  const [sessions, setSessions] = useState([])
  const [fields, setFields] = useState([])
  const [missions, setMissions] = useState([])
  const [form, setForm] = useState({
    device_id: '', field_id: '', mission_id: '', interval_s: '2', minutes: '10', max_shots: '',
  })
  const [busy, setBusy] = useState(false)
  const [stopping, setStopping] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [removingDevice, setRemovingDevice] = useState(null)
  const [error, setError] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const refresh = useCallback(() => {
    Promise.all([api.captureDevices(), api.captureSessions()])
      .then(([d, s]) => {
        setDevices(Array.isArray(d) ? d : [])
        setSessions(Array.isArray(s) ? s : s?.sessions || [])
        setLoaded(true)
      })
      .catch((err) => { setError(err.message); setLoaded(true) })
  }, [])

  useEffect(() => {
    refresh()
    api.fields().then(setFields).catch(() => setFields([]))
    api.missions().then(setMissions).catch(() => setMissions([]))
    const t = setInterval(refresh, REFRESH_MS)
    return () => clearInterval(t)
  }, [refresh])

  const fieldMissions = useMemo(
    () => missions.filter((m) => String(m.field_id) === String(form.field_id)),
    [missions, form.field_id],
  )
  const fieldName = (id) => fields.find((f) => f.id === id)?.name || `Field ${id}`
  const deviceName = (id) => devices.find((d) => d.id === id)?.name || `Device ${id}`

  const chosen = devices.find((d) => String(d.id) === String(form.device_id))
  const warnings = []
  if (chosen) {
    if (!chosen.online) warnings.push('This phone is offline. It will start the session when it next connects.')
    if (!chosen.camera_ready) warnings.push('The phone reports its camera is not ready.')
    if (chosen.battery_pct !== null && chosen.battery_pct < 30 && !chosen.charging) {
      warnings.push(`Phone battery is at ${chosen.battery_pct}%.`)
    }
    if (chosen.gps_accuracy_m !== null && chosen.gps_accuracy_m > 20) {
      warnings.push(`Phone location accuracy is ±${Math.round(chosen.gps_accuracy_m)} m.`)
    }
  }

  async function arm(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await api.armCaptureSession({
        device_id: Number(form.device_id),
        field_id: Number(form.field_id),
        mission_id: form.mission_id ? Number(form.mission_id) : null,
        interval_s: Number(form.interval_s),
        max_duration_s: Math.round(Number(form.minutes) * 60),
        max_shots: form.max_shots ? Number(form.max_shots) : null,
      })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function stop(id) {
    setStopping(id)
    setError(null)
    try {
      await api.stopCaptureSession(id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setStopping(null)
    }
  }

  async function remove(s) {
    const ok = window.confirm(
      `Remove session ${s.id} from this list?\n\n`
      + 'Its photos are kept and stay in Captured images. Only the record of the command goes.',
    )
    if (!ok) return
    setRemoving(s.id)
    try {
      await api.deleteCaptureSession(s.id)
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setRemoving(null)
    }
  }

  // Re-pairing a phone leaves the old row in this list, and arming it does nothing at
  // all. Pick a phone that is actually polling unless the operator chooses otherwise.
  useEffect(() => {
    if (form.device_id) return
    const live = devices.find((d) => d.online)
    if (live) setForm((f) => (f.device_id ? f : { ...f, device_id: String(live.id) }))
  }, [devices, form.device_id])

  async function removeDevice(d) {
    // A device with a session still armed cannot be deleted, and that refusal was the
    // second half of why this never worked: the button was hidden on online phones, and
    // on the rest the server said no for a reason nobody saw. Stop the session here and
    // then delete, so one press does the whole job.
    const extra = d.active_session
      ? `\n\nIts session ${d.active_session.id} is still ${d.active_session.status} and will be stopped.`
      : ''
    const warning = d.online
      ? '\n\nThis phone is online. It will have to pair again before it can be used.'
      : ''
    if (!window.confirm(
      `Remove the pairing "${d.name}"?${extra}${warning}\n\n`
      + 'Flights it already made are kept.')) return

    setRemovingDevice(d.id)
    setError(null)
    try {
      if (d.active_session) {
        await api.stopCaptureSession(d.active_session.id).catch(() => {})
      }
      await api.deleteCaptureDevice(d.id)
      await refresh()
    } catch (e) {
      setError(`Could not remove "${d.name}": ${e.message}`)
    } finally {
      setRemovingDevice(null)
    }
  }

  const expectedShots = Math.floor((Number(form.minutes) * 60) / Math.max(0.3, Number(form.interval_s)))

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Capture"
        icon={Camera}
        title="Drone camera"
        description="Start interval capture on the phone mounted on the drone. Start the session on the ground, before takeoff: the phone keeps capturing if the connection drops, and stops itself at the time limit."
      />

      {error && <div className="as-warn" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="as-grid cols-2" style={{ alignItems: 'start' }}>
        <section>
          <h2>Paired phones</h2>
          {loaded && devices.length === 0 ? (
            <EmptyState icon={Smartphone} title="No phone paired yet">
              On the drone phone, open this site at /camera over HTTPS, sign in as a
              technician, and pair it. It will appear here within a few seconds.
            </EmptyState>
          ) : (
            devices.map((d) => (
              <div key={d.id} className="as-kpi"
                   style={{ borderLeftColor: d.online ? '#648B2F' : '#9AA0A6', marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ fontWeight: 700, color: 'var(--navy)' }}>{d.name}</div>
                  <span className={`as-pill ${d.online ? 'ok' : 'idle'}`}>
                    {d.online ? 'Online' : `Offline, seen ${secondsAgo(d.seconds_since_seen)}`}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 13, marginTop: 8 }}>
                  <span>Camera: {d.camera_ready ? 'ready' : 'not ready'}</span>
                  <span>
                    Battery: {d.battery_pct !== null ? `${d.battery_pct}%` : 'unknown'}
                    {d.charging ? ', charging' : ''}
                  </span>
                  <span>
                    Location: {d.gps_accuracy_m !== null ? `±${Math.round(d.gps_accuracy_m)} m` : 'no fix'}
                  </span>
                </div>
                {d.ignoring_command && (
                  <div className="as-warn" style={{ marginTop: 8, fontSize: 13 }}>
                    This phone is online and polling, but says it is not running the
                    session armed for it. Reload <strong>/camera</strong> on the phone —
                    its own state is stale.
                  </div>
                )}
                {d.reported_state && (
                  <div className="as-muted" style={{ marginTop: 6, fontSize: 12.5 }}>
                    Phone reports: {d.reported_state === 'capturing'
                      ? `capturing for session ${d.reported_session_id}`
                      : 'idle'}
                  </div>
                )}
                {can('admin') && (
                  <button type="button" className="as-btn secondary as-btn-sm"
                          style={{ marginTop: 8 }} disabled={removingDevice === d.id}
                          onClick={() => removeDevice(d)}>
                    <Trash2 size={14} strokeWidth={1.8} />
                    {removingDevice === d.id ? 'Removing…' : 'Remove this pairing'}
                  </button>
                )}
                <Viewfinder deviceId={d.id} deviceName={d.name} online={d.online} />
                {d.active_session && (
                  <div style={{ marginTop: 8, fontSize: 13 }}>
                    <span className={`as-pill ${SESSION_PILL[d.active_session.status]?.[0] || 'idle'}`}>
                      {SESSION_PILL[d.active_session.status]?.[1] || d.active_session.status}
                    </span>
                    {' '}{d.active_session.shots_reported} frames on {fieldName(d.active_session.field_id)}
                  </div>
                )}
              </div>
            ))
          )}
        </section>

        {can('admin', 'technician') && (
          <section>
            <h2>Start a session</h2>
            <IntervalHelper onUse={(v) => setForm((f) => ({ ...f, interval_s: String(v) }))} />
            <form className="as-card plain" onSubmit={arm}>
              <div className="as-field">
                <label className="as-label" htmlFor="s-dev">Phone</label>
                <select id="s-dev" className="as-select" required value={form.device_id}
                        onChange={(e) => setForm({ ...form, device_id: e.target.value })}>
                  <option value="">Choose a paired phone…</option>
                  {devices.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}{d.online
                        ? ' · online'
                        : d.seconds_since_seen == null
                          ? ' · never connected'
                          : ` · last seen ${Math.round(d.seconds_since_seen / 60)} min ago`}
                    </option>
                  ))}
                </select>
              </div>
              <div className="as-field">
                <label className="as-label" htmlFor="s-field">Field being surveyed</label>
                <select id="s-field" className="as-select" required value={form.field_id}
                        onChange={(e) => setForm({ ...form, field_id: e.target.value, mission_id: '' })}>
                  <option value="">Choose a field…</option>
                  {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </div>
              <div className="as-field">
                <label className="as-label" htmlFor="s-mission">Flight record (optional)</label>
                <select id="s-mission" className="as-select" value={form.mission_id}
                        disabled={!form.field_id}
                        onChange={(e) => setForm({ ...form, mission_id: e.target.value })}>
                  <option value="">None</option>
                  {fieldMissions.map((m) => (
                    <option key={m.id} value={m.id}>
                      Flight {m.id}{m.flown_at ? `, ${m.flown_at.slice(0, 16).replace('T', ' ')}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="as-grid" style={{ gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}>
                <div className="as-field">
                  <label className="as-label" htmlFor="s-int">Interval (s)</label>
                  <input id="s-int" type="number" min="0.3" max="60" step="0.1" required
                         className="as-input" value={form.interval_s}
                         onChange={(e) => setForm({ ...form, interval_s: e.target.value })} />
                </div>
                <div className="as-field">
                  <label className="as-label" htmlFor="s-min">Stop after (min)</label>
                  <input id="s-min" type="number" min="1" max="20" required
                         className="as-input" value={form.minutes}
                         onChange={(e) => setForm({ ...form, minutes: e.target.value })} />
                </div>
                <div className="as-field">
                  <label className="as-label" htmlFor="s-shots">Frame limit</label>
                  <input id="s-shots" type="number" min="1" placeholder="None"
                         className="as-input" value={form.max_shots}
                         onChange={(e) => setForm({ ...form, max_shots: e.target.value })} />
                </div>
              </div>
              <p className="as-muted" style={{ fontSize: 12.5, marginTop: 0 }}>
                About {expectedShots} frames. Set the time limit a little longer than the flight,
                shorter than the battery.
              </p>
              {warnings.map((w) => (
                <div key={w} className="as-warn" style={{ marginBottom: 8 }}>{w}</div>
              ))}
              <button className="as-btn" data-busy={busy} disabled={busy}>
                {!busy && <Play size={16} strokeWidth={1.75} />} {busy ? 'Starting…' : 'Start session'}
              </button>
            </form>
          </section>
        )}
      </div>

      <section style={{ marginTop: 28 }}>
        <h2>Sessions</h2>
        {sessions.length === 0 ? (
          <EmptyState icon={Camera} title="No sessions yet">
            Each session you start appears here with its frame count and how it ended.
          </EmptyState>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="as-table">
              <thead>
                <tr>
                  <th>Session</th><th>Phone</th><th>Field</th><th>Interval</th>
                  <th>Frames</th><th>Status</th><th>Ended because</th><th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => {
                  const [tone, label] = SESSION_PILL[s.status] || ['idle', s.status]
                  const live = s.status === 'armed' || s.status === 'running'
                  return (
                    <tr key={s.id}>
                      <td>{s.id}</td>
                      <td>{deviceName(s.device_id)}</td>
                      <td>{fieldName(s.field_id)}</td>
                      <td>{s.interval_s} s</td>
                      <td>
                        {s.shots_reported > 0
                          ? <Link to={`/captures?session=${s.id}`}>{s.shots_reported}</Link>
                          : <span className="as-muted">0</span>}
                      </td>
                      <td><span className={`as-pill ${tone}`}>{label}</span></td>
                      <td className="as-muted">
                        {s.end_reason || ''}
                        {/* The distinction that matters when nothing was captured. */}
                        {!s.phone_ever_reported && !live && (
                          <div className="as-session-note">
                            The phone never picked this up. Check /camera is open and signed
                            in on the same address as this dashboard.
                          </div>
                        )}
                      </td>
                      <td>
                        {live && can('admin', 'technician') && (
                          <button className="as-btn secondary" disabled={stopping === s.id}
                                  onClick={() => stop(s.id)}>
                            <Square size={14} strokeWidth={2} />
                            {stopping === s.id ? 'Stopping…' : 'Stop'}
                          </button>
                        )}
                        <FlightVideo session={s} />
                        {!live && can('admin') && (
                          <button className="as-btn secondary as-btn-sm"
                                  disabled={removing === s.id}
                                  aria-label={`Delete session ${s.id}`}
                                  title="Remove this row. Its photos are kept."
                                  onClick={() => remove(s)}>
                            <Trash2 size={14} strokeWidth={1.8} />
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="as-muted" style={{ fontSize: 12.5 }}>
          Frame counts are what the phone last reported. Frames reach Detections after the
          phone uploads them, which happens once the session ends and it has a connection.
        </p>
      </section>
    </div>
  )
}
