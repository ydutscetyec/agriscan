import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../state/auth'
import {
  STATE, addCapture, countByState, dropVideo, pendingVideos, saveVideo,
} from '../field/db'
import { drainQueue } from '../field/sync'
import { uploadCapture } from '../field/uploader'
import { BrandMark } from '../components/Layout'

/*
 * The drone camera station. Open this page on the phone that is mounted on the drone.
 *
 * Design rule: the link to the website will drop in the air. A laptop hotspot reaches
 * perhaps 30-50 m and rural mobile data is patchy. So once a session starts, everything
 * that matters happens here, on the phone:
 *   - frames are timed by the phone's own clock, not by commands
 *   - each frame is tagged with the phone's GPS at the moment it is taken
 *   - frames queue on the phone and upload after landing
 *   - the session stops itself at its time or shot limit, link or no link
 * The dashboard starts and stops sessions. It never has to reach the phone mid-flight.
 */

const DEVICE_KEY = 'agriscan_capture_device'
const SESSION_KEY = 'agriscan_capture_session'
const POLL_MS = 3000
const UPLOAD_MS = 10000

function readJson(key) {
  try { return JSON.parse(localStorage.getItem(key) || 'null') } catch { return null }
}
function writeJson(key, value) {
  if (value === null) localStorage.removeItem(key)
  else localStorage.setItem(key, JSON.stringify(value))
}
function mmss(seconds) {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function CameraStation() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const secure = typeof window !== 'undefined' && window.isSecureContext

  const [device, setDevice] = useState(() => readJson(DEVICE_KEY))
  const [deviceName, setDeviceName] = useState('')
  const [registering, setRegistering] = useState(false)
  const [watched, setWatched] = useState(false)
  const [camera, setCamera] = useState({ ready: false, error: null, fullRes: false })
  const [gps, setGps] = useState(null)
  const [gpsError, setGpsError] = useState(null)
  const [wake, setWake] = useState('pending')
  const [battery, setBattery] = useState(null)
  const [link, setLink] = useState('unknown')
  const [local, setLocal] = useState(() => readJson(SESSION_KEY))
  const [queue, setQueue] = useState({ waiting: 0, sent: 0 })
  const [message, setMessage] = useState(null)
  const [now, setNow] = useState(Date.now())

  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const recRef = useRef(null)
  const recStartRef = useRef(0)
  const trackRef = useRef([])
  const [pendingVideo, setPendingVideo] = useState(null)
  const [sendingVideo, setSendingVideo] = useState(false)
  const [videoProgress, setVideoProgress] = useState(0)
  const [wire, setWire] = useState(null)
  // Starting from the phone itself. The dashboard arming a session depends on the phone
  // picking the command up on its next poll, and that path has failed repeatedly in the
  // field. Starting here removes it: the phone creates the session and begins at once,
  // and the dashboard watches and can stop it as before.
  const [fields, setFields] = useState([])
  const [own, setOwn] = useState({ field_id: '', interval_s: 2, minutes: 5 })
  const [starting, setStarting] = useState(false)
  const [showWire, setShowWire] = useState(false)
  // A short visible history. Four rounds of this fault were spent guessing at what the
  // phone did; it can simply keep the last few things it did and show them.
  const [events, setEvents] = useState([])
  const logEvent = useCallback((text) => {
    setEvents((e) => [`${new Date().toLocaleTimeString()} ${text}`, ...e].slice(0, 8))
  }, [])
  const imageCaptureRef = useRef(null)
  const gpsRef = useRef(null)
  const batteryRef = useRef(null)
  const cameraReadyRef = useRef(false)
  const localRef = useRef(readJson(SESSION_KEY))
  const pendingReportRef = useRef(null)
  const busyShotRef = useRef(false)
  const timerRef = useRef(null)
  const wakeRef = useRef(null)
  const completedRef = useRef(new Set())
  const deviceRef = useRef(device)

  useEffect(() => { deviceRef.current = device }, [device])

  // ------------------------------------------------------------------ device sensors

  const startCamera = useCallback(async () => {
    setCamera({ ready: false, error: null, fullRes: false })
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 4032 },
          height: { ideal: 3024 },
        },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
      }
      const track = stream.getVideoTracks()[0]
      // ImageCapture.takePhoto() returns a full-resolution still. Without it we fall
      // back to grabbing a video frame, which is lower resolution. Both are labelled.
      let fullRes = false
      if (typeof window.ImageCapture === 'function' && track) {
        try {
          imageCaptureRef.current = new window.ImageCapture(track)
          fullRes = true
        } catch {
          imageCaptureRef.current = null
        }
      }
      cameraReadyRef.current = true
      setCamera({ ready: true, error: null, fullRes })
    } catch (err) {
      cameraReadyRef.current = false
      setCamera({
        ready: false,
        fullRes: false,
        error:
          err && err.name === 'NotAllowedError'
            ? 'Camera permission was refused. Allow it in the browser site settings, then retry.'
            : `Camera unavailable: ${err?.message || 'unknown error'}`,
      })
    }
  }, [])

  const holdWake = useCallback(async () => {
    if (!('wakeLock' in navigator)) { setWake('unsupported'); return }
    try {
      wakeRef.current = await navigator.wakeLock.request('screen')
      setWake('held')
      wakeRef.current.addEventListener('release', () => setWake('released'))
    } catch {
      setWake('released')
    }
  }, [])

  useEffect(() => {
    if (!secure || !device) return undefined

    startCamera()
    holdWake()

    const onVisible = () => { if (document.visibilityState === 'visible') holdWake() }
    document.addEventListener('visibilitychange', onVisible)

    let watchId = null
    if ('geolocation' in navigator) {
      watchId = navigator.geolocation.watchPosition(
        (pos) => {
          const fix = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
            altitude: typeof pos.coords.altitude === 'number' ? pos.coords.altitude : undefined,
            at: Date.now(),
          }
          gpsRef.current = fix
          setGps(fix)
          setGpsError(null)
          // While recording, keep a position track so a frame pulled out of the video
          // later can be placed. Interpolated, never as good as a still's own EXIF.
          if (recRef.current && recRef.current.state === 'recording') {
            trackRef.current.push({
              t: (Date.now() - recStartRef.current) / 1000,
              lat: fix.lat, lon: fix.lon, acc: fix.accuracy,
            })
          }
        },
        (err) => setGpsError(
          err.code === 1
            ? 'Location permission was refused. Frames will be saved without a position.'
            : 'Waiting for a location fix.',
        ),
        { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 },
      )
    } else {
      setGpsError('This browser has no location support.')
    }

    if (navigator.getBattery) {
      navigator.getBattery().then((b) => {
        const update = () => {
          const value = { pct: Math.round(b.level * 100), charging: b.charging }
          batteryRef.current = value
          setBattery(value)
        }
        update()
        b.addEventListener('levelchange', update)
        b.addEventListener('chargingchange', update)
      }).catch(() => {})
    }

    const clock = setInterval(() => setNow(Date.now()), 500)

    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      if (watchId !== null) navigator.geolocation.clearWatch(watchId)
      clearInterval(clock)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      wakeRef.current?.release?.().catch(() => {})
      clearTimeout(timerRef.current)
    }
  }, [secure, device, startCamera, holdWake])

  // ------------------------------------------------------------------ capture engine

  const refreshQueue = useCallback(async () => {
    const counts = await countByState().catch(() => ({}))
    setQueue({
      waiting: (counts[STATE.QUEUED] || 0) + (counts[STATE.FAILED] || 0) + (counts[STATE.UPLOADING] || 0),
      sent: counts[STATE.SYNCED] || 0,
    })
  }, [])

  const grabFrame = useCallback(async () => {
    if (imageCaptureRef.current) {
      try {
        return await imageCaptureRef.current.takePhoto()
      } catch {
        // Some phones refuse takePhoto mid-stream; fall through to a frame grab.
      }
    }
    const video = videoRef.current
    if (!video || !video.videoWidth) throw new Error('camera not ready')
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    return new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('frame encode failed'))), 'image/jpeg', 0.92)
    })
  }, [])

  /* Viewfinder frame: small, cheap, and only sent while an operator is watching.
     Scaled to 480 px and encoded at low quality — about 20 kB, against the several MB
     of a real capture. It is never stored as a photo and never analysed. */
  const sendPreview = useCallback(async () => {
    const video = videoRef.current
    const dev = deviceRef.current
    if (!video || !video.videoWidth || !dev) return
    const scale = Math.min(1, 480 / video.videoWidth)
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.5))
    if (!blob) return
    try {
      await api.sendPreviewFrame(dev.id, blob)
    } catch {
      // A dropped viewfinder frame does not matter; the next poll tries again. It must
      // never interrupt a capture session.
    }
  }, [])

  /* Flight video, recorded alongside the stills.
     The stills remain the detection source: full resolution, EXIF GPS written by the
     camera. This is the reviewable record of the whole flight — continuous, no gaps
     between frames — held on the phone and uploaded after landing, because a 10-minute
     clip is 100-150 MB and must never compete with the stills for the uplink. */
  const startRecording = useCallback((sessionId) => {
    const stream = streamRef.current
    if (!stream || typeof MediaRecorder === 'undefined') return
    // WebM first, deliberately. A recorder set to MP4 hands over nothing until it is
    // stopped, so a crash or a flat battery mid-flight loses the entire clip; WebM
    // delivers a chunk a second, which is what makes the backup below worth anything.
    // MP4 stays as a fallback for browsers that cannot do WebM at all.
    const type = ['video/webm;codecs=vp9', 'video/webm', 'video/mp4']
      .find((t) => MediaRecorder.isTypeSupported?.(t))
    if (!type) return
    try {
      const chunks = []
      const rec = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 4_000_000 })
      const persist = () => {
        if (!chunks.length) return
        const blob = new Blob(chunks, { type: type.split(';')[0] })
        const seconds = Math.round((Date.now() - recStartRef.current) / 1000)
        // Written to the phone's own storage as it records. A disconnect, a crash, the
        // browser being killed in the background — none of them lose more than the last
        // few seconds, and the clip is still here after a reload.
        saveVideo(sessionId, blob, seconds).catch(() => {})
      }
      rec.ondataavailable = (e) => {
        if (e.data?.size) chunks.push(e.data)
      }
      // On a clock rather than a chunk count: if a browser delivers data irregularly,
      // what matters is that whatever exists is on disk every ten seconds.
      const saver = setInterval(persist, 10000)
      rec.onstop = () => {
        clearInterval(saver)
        persist()
        const blob = new Blob(chunks, { type: type.split(';')[0] })
        if (blob.size) {
          setPendingVideo({
            sessionId,
            blob,
            seconds: Math.round((Date.now() - recStartRef.current) / 1000),
          })
        }
      }
      // One chunk a second, so a crash mid-flight still leaves most of the recording.
      rec.start(1000)
      recRef.current = rec
      recStartRef.current = Date.now()
      trackRef.current = []
    } catch {
      // Recording is a bonus. If it will not start, the stills carry on regardless.
    }
  }, [])

  const stopRecording = useCallback(() => {
    const rec = recRef.current
    recRef.current = null
    if (rec && rec.state !== 'inactive') {
      try { rec.stop() } catch { /* already gone */ }
    }
  }, [])

  const finish = useCallback((state, reason) => {
    logEvent(`ended ${localRef.current?.session.id ?? '?'}: ${reason}`)
    stopRecording()
    clearTimeout(timerRef.current)
    timerRef.current = null
    const st = localRef.current
    if (!st) return
    pendingReportRef.current = { session_id: st.session.id, state, shots: st.shots, reason }
    completedRef.current.add(st.session.id)
    localRef.current = null
    writeJson(SESSION_KEY, null)
    setLocal(null)
    setMessage(`${reason}. ${st.shots} frame${st.shots === 1 ? '' : 's'} saved on this phone.`)
    // The track is small and belongs with the session whether or not the video is sent.
    const points = trackRef.current
    if (points.length) {
      api.uploadFlightTrack(st.session.id, points).catch(() => {})
      trackRef.current = []
    }
  }, [stopRecording])

  const takeShot = useCallback(async () => {
    const st = localRef.current
    if (!st || busyShotRef.current) return
    busyShotRef.current = true
    try {
      const blob = await grabFrame()
      const fix = gpsRef.current
      const fresh = fix && Date.now() - fix.at < 10000
      await addCapture({
        blob,
        fieldId: st.session.field_id,
        source: 'drone',
        meta: {
          captureSessionId: st.session.id,
          missionId: st.session.mission_id,
          capturedAt: new Date().toISOString(),
          ...(fresh ? { lat: fix.lat, lon: fix.lon, accuracy: fix.accuracy, altitude: fix.altitude } : {}),
        },
      })
      if (localRef.current && localRef.current.session.id === st.session.id) {
        const next = { ...localRef.current, shots: localRef.current.shots + 1, lastShotAt: Date.now() }
        localRef.current = next
        writeJson(SESSION_KEY, next)
        setLocal(next)
        if (next.session.max_shots && next.shots >= next.session.max_shots) {
          finish('completed', 'Shot limit reached')
        }
      }
    } catch (err) {
      setMessage(`A frame was missed: ${err.message}.`)
    } finally {
      busyShotRef.current = false
    }
  }, [grabFrame, finish])

  const schedule = useCallback((n) => {
    const st = localRef.current
    if (!st) return
    const due = st.startedAt + n * st.session.interval_s * 1000
    timerRef.current = setTimeout(() => {
      const cur = localRef.current
      if (!cur) return
      const elapsed = (Date.now() - cur.startedAt) / 1000
      if (elapsed >= cur.session.max_duration_s) {
        finish('completed', 'Time limit reached')
        return
      }
      // Timed from the start, not from the last shot, so a slow frame does not
      // push every later frame back. A tick that lands mid-capture is skipped.
      takeShot()
      schedule(n + 1)
    }, Math.max(0, due - Date.now()))
  }, [takeShot, finish])

  const startSession = useCallback((session) => {
    startRecording(session.id)
    // Tell the server at once that this phone has the session, rather than waiting for
    // the next poll. Anything that interrupts the phone in between — a reload, a lost
    // sign-in, the page being backgrounded — used to leave the session looking as if it
    // had never been picked up at all, which is exactly what the sessions table kept
    // reporting.
    api.pollCaptureDevice(session.device_id, {
      camera_ready: true,
      local_session_id: session.id,
      session_report: { session_id: session.id, state: 'running', shots: 0 },
    }).catch(() => {})
    logEvent(`started session ${session.id}`)
    const state = { session, startedAt: Date.now(), shots: 0, lastShotAt: null }
    localRef.current = state
    writeJson(SESSION_KEY, state)
    setLocal(state)
    setMessage(null)
    schedule(0)
  }, [schedule, startRecording])

  // Resume after an accidental reload mid-flight, if the session is still in time.
  useEffect(() => {
    const st = localRef.current
    if (!st || !camera.ready || timerRef.current) return
    const elapsed = (Date.now() - st.startedAt) / 1000
    if (elapsed >= st.session.max_duration_s) {
      finish('completed', 'Time limit reached while the page was closed')
      return
    }
    schedule(Math.ceil(elapsed / st.session.interval_s))
  }, [camera.ready, schedule, finish])

  // ------------------------------------------------------------------- server link

  // Shown on the phone so whoever is holding it knows the laptop can see the camera.
  useEffect(() => {
    if (!device) return
    api.fieldsSummary()
      .then((r) => {
        const list = Array.isArray(r) ? r : (r.fields || [])
        setFields(list)
        setOwn((o) => (o.field_id ? o : { ...o, field_id: list[0] ? String(list[0].id) : '' }))
      })
      .catch(() => {})
  }, [device])

  const startHere = useCallback(async () => {
    const dev = deviceRef.current
    if (!dev || starting) return
    if (!own.field_id) {
      setMessage('Choose the field first.')
      return
    }
    if (!cameraReadyRef.current) {
      setMessage('The camera is not ready yet.')
      return
    }
    setStarting(true)
    setMessage(null)
    try {
      const session = await api.armCaptureSession({
        device_id: dev.id,
        field_id: Number(own.field_id),
        interval_s: Number(own.interval_s),
        max_duration_s: Math.round(Number(own.minutes) * 60),
      })
      // Begin immediately rather than waiting for the command to come back round.
      startSession(session)
      setMessage(`Capturing for session ${session.id}.`)
    } catch (err) {
      setMessage(err.message)
    } finally {
      setStarting(false)
    }
  }, [own, starting, startSession])

  // Anything a previous flight left behind — the phone was closed, lost signal, or the
  // upload never happened. Offered again rather than quietly kept forever.
  useEffect(() => {
    pendingVideos()
      .then((rows) => {
        const row = rows[0]
        if (row?.blob?.size) {
          setPendingVideo({ sessionId: row.sessionId, blob: row.blob, seconds: row.seconds })
        }
      })
      .catch(() => {})
  }, [])

  const poll = useCallback(async () => {
    const dev = deviceRef.current
    if (!dev) return
    const report = pendingReportRef.current || (
      localRef.current
        ? { session_id: localRef.current.session.id, state: 'running', shots: localRef.current.shots }
        : null
    )
    try {
      const res = await api.pollCaptureDevice(dev.id, {
        battery_pct: batteryRef.current?.pct ?? null,
        charging: batteryRef.current?.charging ?? null,
        gps_accuracy_m: gpsRef.current ? Math.round(gpsRef.current.accuracy * 10) / 10 : null,
        camera_ready: cameraReadyRef.current,
        // What this phone believes it is doing. Without it, "the phone is polling but
        // the session never starts" is invisible from the dashboard.
        local_session_id: localRef.current?.session.id ?? null,
        session_report: report,
      })
      setLink('ok')
      if (report && report === pendingReportRef.current) pendingReportRef.current = null
      setWatched(Boolean(res.preview_wanted))
      if (res.preview_wanted && cameraReadyRef.current) sendPreview()

      const cmd = res.command || { action: 'idle' }
      // Exactly what the server just said, kept for the diagnostics panel below. Four
      // rounds of this fault have been spent guessing at what the phone received; it
      // can simply show it.
      setWire({
        at: new Date().toLocaleTimeString(),
        action: cmd.action,
        sessionId: cmd.session?.id ?? null,
        localId: localRef.current?.session.id ?? null,
        completed: [...completedRef.current],
        cameraReady: cameraReadyRef.current,
        deviceId: dev.id,
      })
      if (cmd.action === 'capture' && cmd.session) {
        const running = localRef.current
        if (running && running.session.id !== cmd.session.id) {
          // The server is commanding a different session than this phone thinks it is
          // running. Its own state is stale — a session that ended server-side while the
          // phone was offline, say. The server is the authority, so hand over rather than
          // sitting out the new session forever, which is what used to happen.
          finish('completed', 'Replaced by a newer session')
        }
        if (!localRef.current && !completedRef.current.has(cmd.session.id)) {
          if (!cameraReadyRef.current) {
            setMessage('A session was started, but the camera is not ready. Fix the camera to begin.')
          } else {
            startSession(cmd.session)
          }
        }
      } else if (cmd.action === 'idle' && localRef.current) {
        // Only reachable with a working link: the technician pressed Stop.
        finish('completed', 'Stopped from the dashboard')
      }
    } catch (err) {
      setWire((w) => ({ ...(w || {}), at: new Date().toLocaleTimeString(), error: err.message }))
      if (/not registered/i.test(err.message)) {
        writeJson(DEVICE_KEY, null)
        setDevice(null)
      }
      setLink('down')
    }
  }, [sendPreview, startSession, finish])

  useEffect(() => {
    if (!secure || !device) return undefined
    poll()
    const p = setInterval(poll, POLL_MS)
    const u = setInterval(async () => {
      // Never upload during a capture: it competes with the camera for CPU and radio.
      if (!localRef.current && navigator.onLine) {
        await drainQueue(uploadCapture).catch(() => {})
      }
      refreshQueue()
    }, UPLOAD_MS)
    refreshQueue()
    return () => { clearInterval(p); clearInterval(u) }
  }, [secure, device, poll, refreshQueue])

  // ------------------------------------------------------------------ registration

  async function register(event) {
    event.preventDefault()
    if (registering) return
    setRegistering(true)
    setMessage(null)
    try {
      const created = await api.registerCaptureDevice({
        name: deviceName.trim() || 'Drone phone',
        capabilities: {
          imageCapture: typeof window.ImageCapture === 'function',
          wakeLock: 'wakeLock' in navigator,
          battery: 'getBattery' in navigator,
          geolocation: 'geolocation' in navigator,
        },
      })
      const value = { id: created.id, name: created.name }
      writeJson(DEVICE_KEY, value)
      setDevice(value)
    } catch (err) {
      setMessage(err.message)
    } finally {
      setRegistering(false)
    }
  }

  // ------------------------------------------------------------------------ render

  const capturing = Boolean(local)
  const elapsed = capturing ? (now - local.startedAt) / 1000 : 0
  const remaining = capturing ? local.session.max_duration_s - elapsed : 0
  const lowBattery = battery && !battery.charging && battery.pct < 30
  const poorGps = gps && gps.accuracy > 20

  return (
    <div className="cs-shell">
      <header className="cs-top">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BrandMark size={26} />
          <div>
            <div style={{ fontWeight: 700 }}>Drone camera</div>
            <div className="cs-sub">{device ? device.name : 'Not paired'}</div>
          </div>
        </div>
        <button
          className="as-btn secondary"
          disabled={capturing}
          onClick={() => { signOut(); navigate('/login') }}
        >
          Sign out
        </button>
      </header>

      <main className="cs-main">
        {!secure && (
          <div className="cs-alert">
            <strong>This page must be opened over HTTPS.</strong>
            <div style={{ marginTop: 6 }}>
              Browsers block the camera, location and screen wake lock on insecure pages.
              Open the server&rsquo;s HTTPS address instead:
              {' '}<code>https://{window.location.host}/camera</code> if it has one, or the
              address from the tunnel (see DEPLOY.md).
            </div>
            <div style={{ marginTop: 6 }}>
              Testing on the same Wi-Fi without a tunnel: on the laptop run
              {' '}<code>npm run dev:field</code>, open <code>https://&lt;laptop-ip&gt;:5173/camera</code>
              {' '}here, and accept the certificate warning once.
            </div>
          </div>
        )}

        {secure && !device && (
          <form onSubmit={register}>
            <div className="cs-state">Pair this phone</div>
            <p className="cs-sub">
              Give this phone a name so the dashboard can tell it apart. You only do this once.
            </p>
            <input
              className="as-input"
              style={{ padding: 14, fontSize: 16, marginTop: 12 }}
              placeholder="e.g. Drone phone 1"
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
            />
            {message && <div className="cs-alert">{message}</div>}
            <button className="cs-btn go" disabled={registering}>
              {registering ? 'Pairing…' : 'Pair this phone'}
            </button>
            <p className="cs-sub" style={{ marginTop: 12 }}>Signed in as {user?.name}.</p>
          </form>
        )}

        {secure && device && (
          <>
            <div className="cs-sub">
              {capturing ? `Session ${local.session.id}` : 'Status'}
              {link === 'down' && ' · no connection'}
            </div>
            <div className="cs-state">
              {capturing ? 'Capturing' : queue.waiting > 0 ? 'Frames waiting to upload' : 'Ready'}
            </div>
            <div className="cs-sub">
              {capturing
                ? `One frame every ${local.session.interval_s} s. Stops by itself in ${mmss(remaining)}.`
                : 'Waiting for a session from the dashboard.'}
            </div>

            <div className="cs-grid">
              {capturing ? (
                <>
                  <div className="cs-tile">
                    <div className="cs-tile-value">
                      {local.shots}{local.session.max_shots ? ` / ${local.session.max_shots}` : ''}
                    </div>
                    <div className="cs-tile-label">Frames taken</div>
                  </div>
                  <div className="cs-tile">
                    <div className="cs-tile-value">{mmss(remaining)}</div>
                    <div className="cs-tile-label">Time left</div>
                  </div>
                </>
              ) : (
                <>
                  <div className="cs-tile">
                    <div className="cs-tile-value">{queue.waiting}</div>
                    <div className="cs-tile-label">Waiting to upload</div>
                  </div>
                  <div className="cs-tile">
                    <div className="cs-tile-value">{queue.sent}</div>
                    <div className="cs-tile-label">Uploaded</div>
                  </div>
                </>
              )}
              <div className="cs-tile">
                <div className="cs-tile-value">{gps ? `±${Math.round(gps.accuracy)} m` : '—'}</div>
                <div className="cs-tile-label">Location accuracy</div>
              </div>
              <div className="cs-tile">
                <div className="cs-tile-value">
                  {battery ? `${battery.pct}%` : '—'}
                </div>
                <div className="cs-tile-label">
                  Battery{battery?.charging ? ', charging' : ''}
                </div>
              </div>
            </div>

            {lowBattery && !capturing && (
              <div className="cs-alert">
                Battery is below 30%. The camera and GPS drain it fast — charge before flying.
              </div>
            )}
            {poorGps && (
              <div className="cs-alert">
                Location accuracy is ±{Math.round(gps.accuracy)} m. Wait in the open for it to
                improve before takeoff, or frames will be placed imprecisely on the map.
              </div>
            )}
            {message && <div className="cs-note">{message}</div>}

            <video ref={videoRef} className="cs-preview" playsInline muted aria-label="Camera preview" />
            {pendingVideo && (
              <div className="cs-video">
                <div className="cs-video-text">
                  Flight video ready: {Math.round(pendingVideo.blob.size / (1024 * 1024))} MB,
                  {' '}{pendingVideo.seconds}s. Send it on Wi-Fi if you can — it is much
                  larger than the photos.
                </div>
                <div className="cs-video-actions">
                  <button type="button" className="as-btn" disabled={sendingVideo}
                          onClick={async () => {
                            setSendingVideo(true)
                            try {
                              setVideoProgress(0)
                              await api.uploadFlightVideo(
                                pendingVideo.sessionId, pendingVideo.blob, pendingVideo.seconds,
                                setVideoProgress)
                              await dropVideo(pendingVideo.sessionId).catch(() => {})
                              setPendingVideo(null)
                              setMessage('Flight video uploaded.')
                            } catch (err) {
                              setMessage(`Video upload failed: ${err.message}`)
                            } finally {
                              setSendingVideo(false)
                            }
                          }}>
                    {sendingVideo
                      ? `Uploading… ${Math.round(videoProgress * 100)}%`
                      : 'Upload flight video'}
                  </button>
                  <button type="button" className="as-btn secondary" disabled={sendingVideo}
                          onClick={async () => {
                            if (!window.confirm('Delete this flight video from the phone?')) return
                            await dropVideo(pendingVideo.sessionId).catch(() => {})
                            setPendingVideo(null)
                          }}>
                    Discard
                  </button>
                </div>
              </div>
            )}
            {watched && (
              <div className="cs-watched" role="status">
                The dashboard is watching this camera
              </div>
            )}

            <div style={{ marginTop: 12 }}>
              <div className="cs-check">
                <span>Camera</span>
                <span>
                  {camera.ready
                    ? camera.fullRes ? 'Ready, full resolution' : 'Ready, video-frame resolution'
                    : camera.error ? 'Not available' : 'Starting…'}
                </span>
              </div>
              {camera.error && (
                <div className="cs-alert">
                  {camera.error}
                  <button className="cs-btn go" type="button" onClick={startCamera}>Retry camera</button>
                </div>
              )}
              <div className="cs-check">
                <span>Location</span>
                <span>{gps ? `±${Math.round(gps.accuracy)} m` : gpsError || 'Waiting for a fix…'}</span>
              </div>
              <div className="cs-check">
                <span>Screen stays on</span>
                <span>
                  {wake === 'held' ? 'Yes'
                    : wake === 'unsupported' ? 'Not supported — set screen timeout to max'
                    : 'No — tap the screen'}
                </span>
              </div>
              <div className="cs-check">
                <span>Dashboard link</span>
                <span>{link === 'ok' ? 'Connected' : link === 'down' ? 'No connection' : 'Checking…'}</span>
              </div>
            </div>

            {capturing ? (
              <button className="cs-btn stop" type="button"
                      onClick={() => finish('completed', 'Stopped on the phone')}>
                Stop capturing now
              </button>
            ) : (
              <>
                <div className="cs-start">
                  <div className="cs-start-title">Start a capture from this phone</div>
                  <p className="cs-start-note">
                    The dashboard can start one too. This way does not wait to be told —
                    it begins here, straight away.
                  </p>
                  <label className="cs-start-label" htmlFor="own-field">Field</label>
                  <select id="own-field" className="cs-start-input" value={own.field_id}
                          onChange={(e) => setOwn({ ...own, field_id: e.target.value })}>
                    {fields.length === 0 && <option value="">No fields available</option>}
                    {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>
                  <div className="cs-start-row">
                    <div>
                      <label className="cs-start-label" htmlFor="own-int">Every (s)</label>
                      <input id="own-int" className="cs-start-input" type="number"
                             min="0.3" max="60" step="0.1" value={own.interval_s}
                             onChange={(e) => setOwn({ ...own, interval_s: e.target.value })} />
                    </div>
                    <div>
                      <label className="cs-start-label" htmlFor="own-min">For (min)</label>
                      <input id="own-min" className="cs-start-input" type="number"
                             min="1" max="30" value={own.minutes}
                             onChange={(e) => setOwn({ ...own, minutes: e.target.value })} />
                    </div>
                  </div>
                  <button type="button" className="cs-btn cs-start-btn"
                          disabled={starting || !fields.length} onClick={startHere}>
                    {starting ? 'Starting…' : 'Start capturing now'}
                  </button>
                </div>

                <div className="cs-diag">
                  <button type="button" className="cs-diag-toggle"
                          onClick={() => setShowWire((v) => !v)}>
                    {showWire ? 'Hide' : 'Show'} connection details
                  </button>
                  {showWire && (
                    <dl className="cs-diag-list">
                      <dt>This phone is device</dt><dd>#{wire?.deviceId ?? '—'}</dd>
                      <dt>Last reply from server</dt><dd>{wire?.at ?? 'none yet'}</dd>
                      <dt>Server says</dt>
                      <dd>{wire?.error
                        ? `error: ${wire.error}`
                        : wire
                          ? (wire.action === 'capture'
                              ? `capture, session ${wire.sessionId}`
                              : 'idle, no session')
                          : '—'}</dd>
                      <dt>This phone is running</dt>
                      <dd>{wire?.localId ? `session ${wire.localId}` : 'nothing'}</dd>
                      <dt>Already finished here</dt>
                      <dd>{wire?.completed?.length ? wire.completed.join(', ') : 'none'}</dd>
                      <dt>Camera ready</dt><dd>{wire?.cameraReady ? 'yes' : 'no'}</dd>
                    </dl>
                  )}
                  {showWire && (
                    <ul className="cs-diag-log">
                      {events.length === 0
                        ? <li>No session events yet.</li>
                        : events.map((e) => <li key={e}>{e}</li>)}
                    </ul>
                  )}
                </div>

                <div className="cs-note">
                  Mount the phone, keep this page open, and start the capture
                  <strong> before takeoff</strong>. Capture continues if the connection drops,
                  and stops by itself at the time limit. Frames upload after you land.
                </div>
              </>
            )}
          </>
        )}
      </main>
    </div>
  )
}
