import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Volume2, VolumeX } from 'lucide-react'
import introMp4 from '../assets/intro.mp4'
import introWebm from '../assets/intro.webm'
import posterUrl from '../assets/intro-poster.jpg'

/* The AGRISCAN intro.
 *
 * Plays on every page load. Set PLAY_EVERY_VISIT to false for once per device; the
 * "seen" flag is written either way, so that switch needs no other change.
 *
 * It is a splash, not a loading gate: the app loads behind it and is ready long before
 * the ten seconds are up. Skip, Escape, or a tap anywhere ends it at once — and now
 * that it appears on every load, that exit has to stay obvious and immediate.
 *
 * Two codecs. H.264 is what iOS and Safari need; VP9 is what Chromium builds without a
 * licensed H.264 decoder can play, which includes some Android browsers. A phone that
 * can play neither simply does not see the intro: every failure path here ends with the
 * splash closing, never with a stuck white screen.
 */
const PLAY_EVERY_VISIT = true
const VERSION = 2
const SEEN_KEY = `agriscan_intro_seen_v${VERSION}`
const SOUND_KEY = 'agriscan_intro_sound'
// Sound is what the intro is meant to be heard with, so it is the default. Whether the
// browser allows it is a separate question — see the attempt() comment below.
const SOUND_BY_DEFAULT = true

// The video is 10 s. If it stalls on a weak connection, or the browser can decode
// neither codec and never fires a usable error, the splash leaves on its own.
const HARD_LIMIT_MS = 12000
// Nothing has started playing by now: treat it as unplayable rather than wait it out.
const NO_START_MS = 2500

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch { /* private mode; the preference just does not persist */ }
}

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export function shouldPlayIntro(pathname) {
  // Not on the drone camera station: that screen is opened to start a capture session,
  // often with the aircraft already powered, and must come up immediately.
  if (pathname === '/camera') return false
  // Someone who asked their device for reduced motion has asked for this too.
  if (prefersReducedMotion()) return false
  if (PLAY_EVERY_VISIT) return true
  return read(SEEN_KEY) !== '1'
}

/** Whether the intro should try to play with sound. Default on; 'off' only ever gets
 *  written when someone presses the speaker button to silence it. */
export function soundWanted() {
  const stored = read(SOUND_KEY)
  if (stored === 'on') return true
  if (stored === 'off') return false
  return SOUND_BY_DEFAULT
}

export default function Splash() {
  const { pathname } = useLocation()
  const [visible, setVisible] = useState(() => shouldPlayIntro(pathname))
  const [leaving, setLeaving] = useState(false)
  // Starts muted whatever the stored preference says. A browser refuses to autoplay
  // audio nobody asked for, and a refused play() means a frozen first frame.
  const [muted, setMuted] = useState(true)
  // True when sound was wanted and the browser refused it. Turns the speaker icon into
  // a labelled button, because one press is all it needs and nothing else says so.
  const [soundBlocked, setSoundBlocked] = useState(false)
  const videoRef = useRef(null)
  const skipRef = useRef(null)
  const unlockRef = useRef(null)
  // When the gesture that turned the sound on happened. A pointerdown unlocks audio and
  // React has re-rendered by the time the matching click arrives, so without this the
  // same single tap would turn the sound on and then close the intro.
  const unlockedAt = useRef(0)

  const dismiss = useCallback(() => {
    write(SEEN_KEY, '1')
    setLeaving(true)
    // Matches the fade in app.css. The overlay is removed afterwards so it cannot
    // swallow taps meant for the page underneath.
    setTimeout(() => setVisible(false), 420)
  }, [])

  const enableSound = useCallback(() => {
    const video = videoRef.current
    if (!video || !video.muted) return
    video.muted = false
    setMuted(false)
    setSoundBlocked(false)
    write(SOUND_KEY, 'on')
    video.play().catch(() => {})
  }, [])

  const toggleSound = useCallback((event) => {
    // The click is itself the gesture that lets the browser allow audio.
    event.stopPropagation()
    const video = videoRef.current
    if (!video) return
    const wantSound = video.muted
    video.muted = !wantSound
    setMuted(!wantSound)
    setSoundBlocked(false)
    write(SOUND_KEY, wantSound ? 'on' : 'off')
    if (wantSound) video.play().catch(() => {})
  }, [])

  useEffect(() => {
    if (!visible) return undefined
    const video = videoRef.current
    skipRef.current?.focus()

    const onKey = (event) => {
      if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') dismiss()
    }
    window.addEventListener('keydown', onKey)
    const limit = setTimeout(dismiss, HARD_LIMIT_MS)

    // Sound is attempted first on every load. Every browser blocks autoplay with audio
    // until the site has earned it: Chrome allows it once its media engagement score
    // for the origin is high enough, which happens after a few visits where the video
    // was actually watched. Safari and phones generally never allow it unprompted.
    // A rejection falls straight back to muted rather than leaving a still frame on
    // screen, and flags the speaker button so one press fixes it.
    const attempt = async () => {
      if (!video) return
      if (soundWanted()) {
        video.muted = false
        try {
          await video.play()
          setMuted(false)
          return
        } catch {
          video.muted = true
          setMuted(true)
          setSoundBlocked(true)
          // The browser will allow audio the moment this page gets any interaction at
          // all. Listen for the first one anywhere — a click, a key, a touch — and turn
          // the sound on then, so nobody has to find the speaker button.
          const unlock = () => {
            unlockedAt.current = Date.now()
            enableSound()
            window.removeEventListener('pointerdown', unlock, true)
            window.removeEventListener('keydown', unlock, true)
            window.removeEventListener('touchstart', unlock, true)
          }
          window.addEventListener('pointerdown', unlock, true)
          window.addEventListener('keydown', unlock, true)
          window.addEventListener('touchstart', unlock, true)
          unlockRef.current = unlock
        }
      }
      try {
        await video.play()
      } catch {
        dismiss()
      }
    }
    attempt()

    const noStart = setTimeout(() => {
      const v = videoRef.current
      if (!v || v.currentTime === 0 || v.paused) dismiss()
    }, NO_START_MS)

    return () => {
      window.removeEventListener('keydown', onKey)
      clearTimeout(limit)
      clearTimeout(noStart)
      const unlock = unlockRef.current
      if (unlock) {
        window.removeEventListener('pointerdown', unlock, true)
        window.removeEventListener('keydown', unlock, true)
        window.removeEventListener('touchstart', unlock, true)
        unlockRef.current = null
      }
    }
  }, [visible, dismiss, enableSound])

  if (!visible) return null

  return (
    <div
      className={`as-splash${leaving ? ' leaving' : ''}`}
      role="dialog"
      aria-label="AGRISCAN intro"
      onClick={() => {
        // The tap that unblocked the audio is not also a request to close. Skip is
        // right there for anyone who wanted out instead.
        if (Date.now() - unlockedAt.current < 700) return
        const video = videoRef.current
        if (video?.muted && soundWanted()) {
          enableSound()
          return
        }
        dismiss()
      }}
    >
      <video
        ref={videoRef}
        className="as-splash-video"
        poster={posterUrl}
        muted={muted}
        autoPlay
        playsInline
        preload="auto"
        aria-hidden="true"
        onEnded={dismiss}
        onError={dismiss}
      >
        <source src={introWebm} type="video/webm" />
        <source src={introMp4} type="video/mp4" />
      </video>

      <div className="as-splash-controls">
        <button
          type="button"
          className={`as-splash-btn${soundBlocked ? ' wide accent' : ''}`}
          onClick={toggleSound}
          aria-label={muted ? 'Turn sound on' : 'Turn sound off'}
          title={muted ? 'Turn sound on' : 'Turn sound off'}
        >
          {muted ? <VolumeX size={18} strokeWidth={1.75} />
                 : <Volume2 size={18} strokeWidth={1.75} />}
          {soundBlocked && <span className="as-splash-btn-text">Tap for sound</span>}
        </button>
        <button
          ref={skipRef}
          type="button"
          className="as-splash-btn wide as-splash-skip"
          onClick={(event) => { event.stopPropagation(); dismiss() }}
        >
          Skip
        </button>
      </div>
    </div>
  )
}
