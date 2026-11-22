import { useRef, useState } from 'react'
import { Download, Film, ImageDown, MapPin, X } from 'lucide-react'
import { api, flightVideoUrl } from '../api/client'

/* The flight video for one session, with a way to pull any frame out of it.
 *
 * A frame saved from here is NOT a camera still. It is roughly a sixth of the pixels,
 * inter-frame compressed, and its position is interpolated from the 1 Hz track rather
 * than written by the camera. The server marks it `video_interpolated` for exactly that
 * reason, and this says so before you press the button rather than after.
 */
export default function FlightVideo({ session, onSaved }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const [src, setSrc] = useState(null)
  const [ext, setExt] = useState('webm')
  const [interval, setInterval_] = useState(1)
  const videoRef = useRef(null)

  async function show() {
    setOpen(true)
    if (src) return
    try {
      // The video endpoint needs the auth header, so it cannot go straight into <video
      // src>. A blob URL loses Range support and pulls the whole clip, which is fine for
      // a ten-minute flight and wrong for an hour-long one — worth revisiting if clips
      // get much longer.
      const response = await fetch(flightVideoUrl(session.id), {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('agriscan_token')}` },
      })
      if (!response.ok) throw new Error(`Could not load the video (${response.status})`)
      const blob = await response.blob()
      // CameraStation records WebM where it can and falls back to MP4, so name the
      // download after what actually came back rather than assuming either one.
      setExt(blob.type.includes('mp4') ? 'mp4' : 'webm')
      setSrc(URL.createObjectURL(blob))
    } catch (err) {
      setNote({ bad: true, text: err.message })
    }
  }

  async function saveFrame() {
    const video = videoRef.current
    if (!video || busy) return
    setBusy(true)
    setNote(null)
    try {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      canvas.getContext('2d').drawImage(video, 0, 0)
      const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.92))
      const result = await api.saveVideoFrame(session.id, video.currentTime.toFixed(2), blob)
      setNote({
        text: result.duplicate
          ? `That frame was already saved as image #${result.image_id}.`
          : `Saved as image #${result.image_id}`
            + (result.lat === null
              ? ', with no position: this flight has no track.'
              : ', position interpolated from the flight track.'),
      })
      onSaved?.()
    } catch (err) {
      setNote({ bad: true, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  if (!session.has_video) return null

  const mb = session.video_bytes ? Math.round(session.video_bytes / (1024 * 1024)) : null

  if (!open) {
    return (
      <button type="button" className="as-btn secondary as-btn-sm" onClick={show}>
        <Film size={14} strokeWidth={1.8} /> Video{mb ? ` (${mb} MB)` : ''}
      </button>
    )
  }

  /* Queued, not done here: a five-minute clip is a full decode pass and hundreds of
     writes. The worker does it and each frame it writes queues its own analysis. */
  async function extractFrames() {
    if (busy) return
    const seconds = Number(interval)
    const estimate = session.video_duration_s
      ? Math.floor(session.video_duration_s / seconds)
      : null
    const ok = window.confirm(
      `Pull a frame every ${seconds}s from this flight?\n\n`
      + (estimate ? `That is about ${estimate} frames, each analysed separately.\n\n` : '')
      + (session.track_points
        ? 'Positions are interpolated from the flight track and marked as such.'
        : 'This session has NO track, so the frames will have no position and will '
          + 'not appear on the map.'),
    )
    if (!ok) return
    setBusy(true)
    setNote(null)
    try {
      const r = await api.extractFrames(session.id, seconds)
      setNote({
        text: `Queued as job ${r.job_id}: about ${r.estimated_frames ?? '?'} frames `
          + `every ${r.interval_s}s. They appear in Captured images as the worker `
          + 'works through them.',
      })
    } catch (err) {
      setNote({ bad: true, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="as-flightvid">
      <div className="as-flightvid-head">
        <span>Flight video · session {session.id}</span>
        <button type="button" className="as-tour-close" onClick={() => setOpen(false)}
                aria-label="Close the video">
          <X size={17} strokeWidth={1.75} />
        </button>
      </div>

      {src
        ? <video ref={videoRef} className="as-flightvid-player" src={src} controls playsInline />
        : <div className="as-flightvid-loading">Loading the video…</div>}

      <p className="as-flightvid-warn">
        Frames taken from video are lower resolution than the captured stills and their
        position is interpolated from the flight track. They are marked as such and should
        not be treated as ground truth.
      </p>

      <div className="as-flightvid-actions">
        <button type="button" className="as-btn as-btn-sm" disabled={!src || busy}
                onClick={saveFrame}>
          <ImageDown size={15} strokeWidth={1.8} />
          {busy ? 'Saving…' : 'Save this frame'}
        </button>
        {/* The blob is already in memory for the player, so the download costs nothing
            extra -- no second request, and it works offline once the clip has loaded.
            A plain href to the API would 401: that endpoint needs the auth header. */}
        <a className={`as-btn as-btn-sm secondary${src ? '' : ' as-disabled'}`}
           href={src || undefined}
           download={`agriscan-flight-${session.id}.${ext}`}
           aria-disabled={!src}
           onClick={(e) => { if (!src) e.preventDefault() }}>
          <Download size={15} strokeWidth={1.8} />
          Download video
        </a>
        <span className="as-flightvid-every">
          <label htmlFor="as-frame-every">Frame every</label>
          <select id="as-frame-every" value={interval} disabled={busy}
                  onChange={(e) => setInterval_(e.target.value)}>
            <option value="0.3">0.3s</option>
            <option value="0.5">0.5s</option>
            <option value="1">1s (one per GPS fix)</option>
            <option value="2">2s</option>
            <option value="5">5s</option>
            <option value="10">10s</option>
          </select>
          <button type="button" className="as-btn as-btn-sm secondary" disabled={busy}
                  onClick={extractFrames}>
            <MapPin size={15} strokeWidth={1.8} />
            Extract to map
          </button>
        </span>
        {session.track_points
          ? <span className="as-muted" style={{ fontSize: 12.5 }}>
              {session.track_points} track points
            </span>
          : <span className="as-muted" style={{ fontSize: 12.5 }}>
              No flight track — saved frames will have no position.
            </span>}
      </div>

      {note && (
        <div className={note.bad ? 'as-warn' : 'as-note'} role="status" style={{ marginTop: 10 }}>
          {note.text}
        </div>
      )}
    </div>
  )
}
