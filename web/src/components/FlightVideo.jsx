import { useRef, useState } from 'react'
import { Film, ImageDown, X } from 'lucide-react'
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
      setSrc(URL.createObjectURL(await response.blob()))
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
