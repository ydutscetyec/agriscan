import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../state/auth'
import { Pause, Play, X } from 'lucide-react'
import { Bi } from '../field/labels'

/* A guided walk through every page the signed-in role can open.
 *
 * The tour drives the router: each step navigates to a real page and explains the page
 * you are looking at, with an arrow pointing at the control that opens it.
 *
 * The anchors are the navigation itself — the sidebar link for each page, the account
 * chip, the field client's tab bar. Those are the one part of the interface that cannot
 * quietly move or be renamed without the route changing too, which is what makes
 * pointing at them safe. Anything that is not on screen (the sidebar is a closed drawer
 * on a phone) simply has no arrow: the panel docks to the bottom and the tour carries on.
 *
 * Steps are filtered by role using the same lists App.jsx enforces, so nobody is walked
 * into a page that will refuse them.
 *
 * Progress is kept per device and per account, so a farmer borrowing a technician's
 * phone gets their own tour. It is not in the database: that avoids another migration
 * and another endpoint, at the cost of replaying if someone clears their browser data.
 * Harmless, and the ? button means the flag is never the only way back in.
 */
const VERSION = 2
const seenKey = (userId) => `agriscan_guide_v${VERSION}_u${userId}`
/* The tour opens by itself every time someone signs in, not only the first time. Set
   this to false for once per account per device; the "seen" flag is written either way,
   so the switch needs no other change.

   Deliberately tied to signing in and not to loading the page. Opening on every load
   would mean a reload anywhere in the app threw the tour back up and navigated the
   person to the Overview, which makes the site close to unusable. */
const START_EVERY_SIGN_IN = true

const ALL = ['admin', 'technician', 'researcher']
const STAFF = ['admin', 'technician']

function hasSeen(userId) {
  try {
    return localStorage.getItem(seenKey(userId)) === '1'
  } catch {
    return true
  }
}

function markSeen(userId) {
  try {
    localStorage.setItem(seenKey(userId), '1')
  } catch { /* replays next time; not worth reporting */ }
}

/* Dashboard tour, in sidebar order so it matches what the person is looking at. */
const DASHBOARD_TOUR = [
  {
    path: '/',
    anchor: '.as-navlink[href="/"]',
    title: 'Overview',
    body: 'Every image on the path from capture to a technician-verified result. The four '
      + 'counts are the four stages, and nothing reaches a farmer as advice until the last one.',
  },
  {
    path: '/map',
    anchor: '.as-navlink[href="/map"]',
    title: 'Map',
    body: 'Fields and detections by location, from the GPS written into each photo. Use it '
      + 'to see whether a problem is spreading across one corner of a field or the whole barangay.',
  },
  {
    path: '/detections',
    anchor: '.as-navlink[href="/detections"]',
    title: 'Detections',
    body: 'Everything the model has found, newest first, filterable by field, condition and date. '
      + 'A row here is model output: it is not advice until a technician has verified it.',
  },
  {
    path: '/verify',
    anchor: '.as-navlink[href="/verify"]',
    roles: ALL,
    title: 'Verification queue',
    body: 'The gate. Each item shows the photo, what the model found and how confident it was. '
      + 'Confirm, correct or reject. Your decisions are the ground truth the model is measured '
      + 'against in Chapter 4, so a careless confirmation damages the evaluation as much as the farmer.',
  },
  {
    path: '/recommendations',
    anchor: '.as-navlink[href="/recommendations"]',
    roles: ALL,
    title: 'Recommendations',
    body: 'Suggested countermeasures, generated from the condition, severity and growth stage. '
      + 'They are drafts. Check each against DA or PhilRice guidance before approving, because an '
      + 'approved recommendation is what someone acts on in a real field.',
  },
  {
    path: '/drone-camera',
    anchor: '.as-navlink[href="/drone-camera"]',
    roles: STAFF,
    title: 'Drone camera',
    body: 'Arm and trigger the phone mounted on the aircraft, and watch photos arrive during a '
      + 'flight. The phone itself opens /camera and needs an https address — over plain http the '
      + 'browser will not give it the camera or GPS at all.',
  },
  {
    path: '/captures',
    anchor: '.as-navlink[href="/captures"]',
    title: 'Captured images',
    body: 'Every photo on this server, analysed or not. Detections only lists model output, '
      + 'so a photo still queued, rejected by the quality gate, or judged not to be palay '
      + 'shows up here and nowhere else. This is where to look when the Overview counts an '
      + 'image you cannot find.',
  },
  {
    path: '/missions',
    anchor: '.as-navlink[href="/missions"]',
    title: 'Flight records',
    body: 'One row per flight: when, which field, which aircraft, how many images. This is the '
      + 'provenance trail that lets you say where a dataset came from months later.',
  },
  {
    path: '/aircraft',
    anchor: '.as-navlink[href="/aircraft"]',
    title: 'The aircraft',
    body: 'The airframe, payload and flight parameters the system assumes, with the altitude and '
      + 'overlap the capture plan is built around.',
  },
  {
    path: '/upload',
    anchor: '.as-navlink[href="/upload"]',
    roles: ALL,
    title: 'Upload images',
    body: 'Bring in photos taken outside a live session — an SD card after a flight, or a phone '
      + 'that was offline. They join the same queue and the same verification gate.',
  },
  {
    path: '/field-boundaries',
    anchor: '.as-navlink[href="/field-boundaries"]',
    title: 'Field boundaries',
    body: 'Draw each field once. A detection with no boundary to fall inside cannot be placed on '
      + 'the map or counted per field, so this is worth doing before the first flight rather than after.',
  },
  {
    path: '/fields',
    anchor: '.as-navlink[href="/fields"]',
    title: 'Manage fields',
    body: 'Farms, their fields, variety and planting date. Growth stage is worked out from the '
      + 'planting date, and growth stage is what makes a recommendation specific rather than generic.',
  },
  {
    path: '/farmers',
    anchor: '.as-navlink[href="/farmers"]',
    roles: ALL,
    title: 'Farmers',
    body: 'The people the results are for, and which fields belong to each. A farmer only ever '
      + 'sees their own fields, and that is enforced on the server.',
  },
  {
    path: '/analytics',
    anchor: '.as-navlink[href="/analytics"]',
    roles: ALL,
    title: 'Analytics',
    body: 'Condition counts, trends and model performance. Verified and unverified detections are '
      + 'kept apart everywhere here; do not merge them in a result you intend to publish.',
  },
  {
    path: '/models',
    anchor: '.as-navlink[href="/models"]',
    title: 'Models',
    body: 'Every registered model, its dataset version and whether it is in production. A new model '
      + 'starts NOT_VALIDATED and stays there until enough technician-verified results exist to '
      + 'measure it. Until one is in production, photos upload and wait.',
  },
  {
    path: '/users',
    anchor: '.as-navlink[href="/users"]',
    roles: ['admin'],
    title: 'Users',
    body: 'Accounts and roles. Technician is the role that gates what farmers are told, so give it '
      + 'only to a qualified agricultural technician. Roles are enforced on the server — hiding a '
      + 'page never grants or removes access.',
  },
  {
    path: '/account',
    anchor: '.as-userchip',
    title: 'Your account',
    body: 'Change your own password here. Doing so signs out every other device on this account and '
      + 'keeps the one you are using. That is the first thing to do with a password someone handed you.',
  },
]

/* Field client tour. Titles are bilingual because this is the farmer's interface. */
const FIELD_TOUR = [
  {
    path: '/field',
    anchor: '.fc-tab[href="/field"]',
    label: 'capture',
    body: 'Pick the field, then take the photo. Stand close enough that one plant fills most of the '
      + 'picture, hold steady, and keep the sun behind you. The app checks each photo and tells you '
      + 'if it is too blurry or too dark, while you are still standing there.',
  },
  {
    path: '/field/results',
    anchor: '.fc-tab[href="/field/results"]',
    label: 'myResults',
    body: 'Every photo you have sent and what came back. Until a technician has checked it, a result '
      + 'says pending — that is not advice yet. When one is ready, open it and tell the app whether '
      + 'it matches what you see. Say so even when the answer is no; that is how a mistake gets found.',
  },
  {
    path: '/field/account',
    anchor: '.fc-account-link',
    label: 'account',
    body: 'Your name, your barangay, and your password. Photos taken with no signal stay on the phone '
      + 'and send themselves when signal returns, so do not clear this app\u2019s data while the top of '
      + 'the screen still says some are waiting.',
  },
]

export function tourForRole(role) {
  if (role === 'farmer') return FIELD_TOUR
  return DASHBOARD_TOUR.filter((step) => !step.roles || step.roles.includes(role))
}

/* The tour state lives above the router, not inside a shell.
 *
 * RequireAuth renders its own <AppShell> per route, so the shell is unmounted and
 * remounted on every navigation. State held there was reset to step 1 by the tour's own
 * navigation, and the tour could never advance past the second page. */
const TourContext = createContext({ start: () => {} })

export function useTour() {
  return useContext(TourContext)
}

export function OnboardingProvider({ children }) {
  const { user, signInCount } = useAuth()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const checked = useRef(null)
  const lastSignIn = useRef(0)

  useEffect(() => {
    if (!user) {
      checked.current = null
      // Signing out has to stop the tour. It keeps calling navigate() on every step,
      // and a tour still running after sign-out drags the browser off the sign-in page
      // every few seconds, clearing whatever has been typed into it.
      setOpen(false)
      return
    }
    // Never on the drone camera station. That page is opened with the aircraft powered,
    // and a tour that navigates away from it takes the phone off the station entirely —
    // which looks exactly like a phone that will not pair.
    if (pathname === '/camera') {
      setOpen(false)
      return
    }
    const freshSignIn = signInCount > lastSignIn.current
    lastSignIn.current = signInCount
    const firstTimeOnThisDevice = checked.current !== user.id && !hasSeen(user.id)
    checked.current = user.id
    if ((freshSignIn && START_EVERY_SIGN_IN) || firstTimeOnThisDevice) setOpen(true)
  }, [user, signInCount, pathname])

  const close = useCallback(() => {
    if (user) markSeen(user.id)
    setOpen(false)
  }, [user])

  const value = useMemo(() => ({ start: () => setOpen(true) }), [])

  return (
    <TourContext.Provider value={value}>
      {children}
      <Tour user={user} open={open} onClose={close} />
    </TourContext.Provider>
  )
}

/* The tour runs by itself. Each step is timed from how much there is to read, with a
   floor so a short step is never a flash, and a pause button for anyone who wants to
   stop and look at the page. Pressing Back or Next also pauses: someone steering by
   hand should not be shoved onward mid-sentence. */
const AUTO_ADVANCE = true
const READING_WORDS_PER_SECOND = 3.2
const MIN_STEP_MS = 7000
const MAX_STEP_MS = 20000

export function stepDuration(step) {
  const words = `${step.title || ''} ${step.body}`.trim().split(/\s+/).length
  const ms = (words / READING_WORDS_PER_SECOND) * 1000
  return Math.round(Math.min(MAX_STEP_MS, Math.max(MIN_STEP_MS, ms)))
}

const PANEL_WIDTH = 440
const GAP = 16
const EDGE = 12

/** Where to put the panel relative to the thing it is pointing at. */
function placeNear(rect, panel) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const height = panel?.offsetHeight || 260
  const width = Math.min(PANEL_WIDTH, vw - EDGE * 2)
  const clamp = (v, min, max) => Math.max(min, Math.min(v, max))

  // Sitting low on the screen (the field client's tab bar): go above it.
  if (rect.top > vh * 0.55) {
    const left = clamp(rect.left + rect.width / 2 - width / 2, EDGE, vw - width - EDGE)
    return {
      side: 'above',
      style: { top: Math.max(EDGE, rect.top - height - GAP), left, width },
      arrow: clamp(rect.left + rect.width / 2 - left, 24, width - 24),
    }
  }
  // Narrow and on the left (a sidebar link): go to its right.
  if (rect.right < vw * 0.45 && vw - rect.right > width + GAP + EDGE) {
    const top = clamp(rect.top + rect.height / 2 - height / 2, EDGE, vh - height - EDGE)
    return {
      side: 'right',
      style: { top, left: rect.right + GAP, width },
      arrow: clamp(rect.top + rect.height / 2 - top, 24, height - 24),
    }
  }
  // Otherwise below it (the account chip in the top bar).
  const left = clamp(rect.right - width, EDGE, vw - width - EDGE)
  return {
    side: 'below',
    style: { top: Math.min(rect.bottom + GAP, vh - height - EDGE), left, width },
    arrow: clamp(rect.left + rect.width / 2 - left, 24, width - 24),
  }
}

/** The ring sits 6px outside the control. A sidebar link starts at x=0, so without
 *  clamping its left border would be drawn off the edge of the screen and never seen. */
function ringBox(rect) {
  const pad = 6
  const left = Math.max(2, rect.left - pad)
  const top = Math.max(2, rect.top - pad)
  return {
    top,
    left,
    width: Math.min(rect.right + pad, window.innerWidth - 2) - left,
    height: Math.min(rect.bottom + pad, window.innerHeight - 2) - top,
  }
}

function Tour({ user, open, onClose }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [index, setIndex] = useState(0)
  const [spot, setSpot] = useState(null)
  const [playing, setPlaying] = useState(AUTO_ADVANCE)
  const [elapsed, setElapsed] = useState(0)
  const steps = useMemo(() => tourForRole(user?.role), [user?.role])
  const panelRef = useRef(null)

  const step = steps[index]
  const last = index === steps.length - 1

  // Navigating is the whole point of the tour: the explanation is about the page the
  // person can see behind the panel.
  useEffect(() => {
    if (open && user && step) navigate(step.path)
  }, [open, user, step, navigate])

  useEffect(() => {
    if (open) {
      setIndex(0)
      setPlaying(AUTO_ADVANCE)
    }
  }, [open])

  // Auto-advance. The bar under the text is this timer, so what is about to happen is
  // visible rather than a surprise.
  useEffect(() => {
    if (!open || !playing || !step) return undefined
    const total = stepDuration(step)
    const startedAt = Date.now()
    setElapsed(0)
    const tick = setInterval(() => {
      const ratio = (Date.now() - startedAt) / total
      if (ratio >= 1) {
        clearInterval(tick)
        if (last) onClose()
        else setIndex((i) => i + 1)
      } else {
        setElapsed(ratio)
      }
    }, 100)
    return () => clearInterval(tick)
  }, [open, playing, step, last, onClose])

  const goTo = useCallback((next) => {
    // Taking the wheel stops the clock.
    setPlaying(false)
    setIndex(next)
  }, [])

  // Someone who starts using the page has stopped watching the tour. Without this, a
  // technician who signs in to clear the verification queue is navigated away from it
  // every twelve seconds for three minutes, and has to find Skip before they can work.
  // The tour stays on screen so it can be resumed; it just stops driving.
  useEffect(() => {
    if (!open || !playing) return undefined
    const onInteract = (event) => {
      if (event.target.closest?.('.as-tour')) return
      setPlaying(false)
    }
    window.addEventListener('pointerdown', onInteract, true)
    window.addEventListener('keydown', onInteract, true)
    return () => {
      window.removeEventListener('pointerdown', onInteract, true)
      window.removeEventListener('keydown', onInteract, true)
    }
  }, [open, playing])

  // Find the control this step is about and follow it. The page under the tour is still
  // loading when the step changes, so this retries briefly rather than giving up on the
  // first miss, and keeps watching for scroll, resize and the drawer opening.
  useEffect(() => {
    if (!open || !step) return undefined
    let frame = 0
    let stopped = false
    let lastKey = ''
    let scrolled = false

    const measure = () => {
      if (stopped) return
      const target = step.anchor ? document.querySelector(step.anchor) : null
      // The sidebar scrolls. On a short screen the last links — Models, Users — sit
      // below its fold, so the arrow pointed at something the person could not see.
      // Bring the anchor into view inside its own scroll container first. 'nearest'
      // leaves it alone when it is already visible, so nothing jumps between steps.
      if (target && !scrolled) {
        scrolled = true
        target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      }
      const rect = target?.getBoundingClientRect()
      // Horizontal matters as much as vertical: a closed sidebar drawer is still in the
      // DOM, just translated off the left edge, and pointing an arrow at it would point
      // the person at nothing.
      const onScreen = rect && rect.width > 0 && rect.height > 0
        && rect.bottom > 0 && rect.top < window.innerHeight
        && rect.right > 0 && rect.left < window.innerWidth
      // A frame loop, because the thing being pointed at moves for reasons there is no
      // event for: a lazy page finishing its mount, the sidebar drawer sliding open, a
      // list growing under it. Re-rendering only when the rectangle actually changes
      // keeps that to a few renders per step instead of sixty a second.
      const key = onScreen
        ? `${Math.round(rect.top)}:${Math.round(rect.left)}:${Math.round(rect.width)}:${Math.round(rect.height)}`
        : ''
      if (key !== lastKey) {
        lastKey = key
        setSpot(onScreen ? { rect, ...placeNear(rect, panelRef.current) } : null)
      }
      frame = requestAnimationFrame(measure)
    }
    frame = requestAnimationFrame(measure)
    return () => {
      stopped = true
      cancelAnimationFrame(frame)
    }
  }, [open, step, pathname])

  useEffect(() => {
    if (!open) return undefined
    panelRef.current?.focus()
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !user || !step || pathname === '/camera') return null

  // No anchor on screen: dock it instead of pointing at nothing.
  const docked = !spot
  const variant = pathname.startsWith('/field') ? 'field' : 'dashboard'
  const panelStyle = spot
    ? { ...spot.style, position: 'fixed' }
    : undefined
  const arrowStyle = spot
    ? (spot.side === 'right'
      ? { top: spot.arrow }
      : { left: spot.arrow })
    : undefined

  return (
    <>
      {spot && (
        <div
          className="as-tour-ring"
          aria-hidden="true"
          style={ringBox(spot.rect)}
        />
      )}
      <aside
        className={`as-tour ${docked ? `docked ${variant}` : `anchored ${spot.side}`}`}
        style={panelStyle}
        role="dialog"
        aria-label="Guided tour"
        aria-live="polite"
        ref={panelRef}
        tabIndex={-1}
      >
        {spot && <span className="as-tour-arrow" style={arrowStyle} aria-hidden="true" />}

        <div className="as-tour-head">
          <span className="as-tour-count">Step {index + 1} of {steps.length}</span>
          <button type="button" className="as-tour-close" onClick={onClose}
                  aria-label="End the tour">
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        <h2 className="as-tour-title">
          {step.label ? <Bi k={step.label} /> : step.title}
        </h2>
        <p className="as-tour-body">{step.body}</p>

        <div className="as-tour-progress" aria-hidden="true">
          <span className="as-tour-progress-steps"
                style={{ width: `${(index / steps.length) * 100}%` }} />
          <span
            className="as-tour-progress-now"
            style={{
              left: `${(index / steps.length) * 100}%`,
              width: `${((playing ? elapsed : 1) / steps.length) * 100}%`,
            }}
          />
        </div>

        <div className="as-tour-actions">
          <button type="button" className="as-btn ghost" onClick={onClose}>
            {last ? 'Close' : 'Skip tour'}
          </button>
          <div className="as-tour-nav">
            <button
              type="button"
              className="as-btn secondary as-tour-play"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause the tour' : 'Play the tour'}
              title={playing ? 'Pause the tour' : 'Play the tour'}
            >
              {playing ? <Pause size={16} strokeWidth={2} />
                       : <Play size={16} strokeWidth={2} />}
            </button>
            {index > 0 && (
              <button type="button" className="as-btn secondary"
                      onClick={() => goTo(index - 1)}>
                Back
              </button>
            )}
            <button
              type="button"
              className="as-btn"
              onClick={() => (last ? onClose() : goTo(index + 1))}
            >
              {last ? 'Finish' : 'Next'}
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
