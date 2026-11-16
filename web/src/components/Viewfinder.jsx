import { useCallback, useEffect, useRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { devicePreviewUrl } from '../api/client'

/* Near-live view of what a paired phone is pointing at.
 *
 * Not video. One small JPEG every couple of seconds, pulled while this is on screen.
 * The phone is only told to send frames while someone is actually here, so a flight
 * nobody is watching costs no data at all.
 *
 * The age of the frame is always on screen. A viewfinder that silently shows a stale
 * picture is worse than none: an operator would trust it while aiming at nothing.
 */
const REFRESH_MS = 2000
const STALE_AFTER_S = 8

export default function Viewfinder({ deviceId, deviceName, online }) {
  const [src, setSrc] = useState(null)
  // Age of the frame itself, from the server. Not the age of our request: the server
  // happily serves the same file forever, so a phone that died mid-flight would look
  // live if we timed our own fetches. That is the one failure this must not have.
  const [frameAge, setFrameAge] = useState(null)
  const [error, setError] = useState(null)
  const [on, setOn] = useState(false)
  const objectUrl = useRef(null)

  const pull = useCallback(async () => {
    try {
      const response = await fetch(`${devicePreviewUrl(deviceId)}?t=${Date.now()}`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('agriscan_token')}` },
        cache: 'no-store',
      })
      if (response.status === 404) {
        setError('waiting')
        return
      }
      if (!response.ok) throw new Error(String(response.status))
      const age = Number(response.headers.get('X-Frame-Age-Seconds'))
      const blob = await response.blob()
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = URL.createObjectURL(blob)
      setSrc(objectUrl.current)
      setFrameAge(Number.isFinite(age) ? age : null)
      setError(null)
    } catch {
      setError('unreachable')
    }
  }, [deviceId])

  useEffect(() => {
    if (!on) return undefined
    pull()
    const timer = setInterval(pull, REFRESH_MS)
    return () => clearInterval(timer)
  }, [on, pull])

  useEffect(() => () => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
  }, [])

  const stale = frameAge !== null && frameAge > STALE_AFTER_S

  return (
    <div className="as-vf">
      <div className="as-vf-head">
        <span className="as-vf-title">Viewfinder · {deviceName}</span>
        <button type="button" className="as-btn secondary as-btn-sm" onClick={() => setOn((v) => !v)}>
          {on ? <><EyeOff size={15} strokeWidth={1.8} /> Stop</>
              : <><Eye size={15} strokeWidth={1.8} /> Show camera</>}
        </button>
      </div>

      {!on && (
        <p className="as-vf-note">
          Shows what this phone&rsquo;s camera sees, refreshed about every two seconds.
          The phone only sends frames while this is open, so leave it closed to save the
          phone&rsquo;s data and battery.
        </p>
      )}

      {on && (
        <>
          <div className={`as-vf-frame${stale ? ' stale' : ''}`}>
            {src ? <img src={src} alt="Latest frame from the drone phone" />
                 : <div className="as-vf-empty">
                     {error === 'waiting'
                       ? 'Waiting for the first frame. The phone sends one within a few seconds of this opening.'
                       : error === 'unreachable'
                         ? 'Cannot reach the server.'
                         : 'Connecting…'}
                   </div>}
          </div>
          <p className={`as-vf-status${stale ? ' stale' : ''}`}>
            {!online && 'This phone is offline. '}
            {src && (stale
              ? `Last frame ${frameAge}s ago — the phone has stopped sending.`
              : 'Updating every 2 seconds. This is a series of still frames, not live video.')}
          </p>
        </>
      )}
    </div>
  )
}
