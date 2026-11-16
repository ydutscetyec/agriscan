/**
 * p22: when the intro is allowed to play, and whether the guide has usable content for
 * every role. Rendering is not covered here (the suite runs without a DOM); these are
 * the decisions that would otherwise only be caught by a person watching the screen.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { L } from '../field/labels'

function memoryStorage() {
  const map = new Map()
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
    clear: () => map.clear(),
  }
}

function fakeWindow({ reducedMotion = false } = {}) {
  return {
    matchMedia: (query) => ({
      matches: reducedMotion && query.includes('prefers-reduced-motion'),
    }),
  }
}

let shouldPlayIntro
let soundWanted
let tourForRole
let stepDuration

beforeEach(async () => {
  globalThis.localStorage = memoryStorage()
  // The tour module now reaches the auth state, which reads a stored token on import.
  globalThis.sessionStorage = memoryStorage()
  globalThis.window = fakeWindow()
  ;({ shouldPlayIntro, soundWanted } = await import('../components/Splash'))
  ;({ tourForRole, stepDuration } = await import("../components/Onboarding"))
})

afterEach(() => {
  delete globalThis.localStorage
  delete globalThis.sessionStorage
  delete globalThis.window
})

describe('intro splash', () => {
  it('plays on a first visit', () => {
    expect(shouldPlayIntro('/')).toBe(true)
  })

  it('plays again on every later visit', () => {
    // The p23 choice: the intro is part of entering the site, not a one-off. Skip,
    // Escape or a tap still ends it immediately, which is what keeps that bearable.
    expect(shouldPlayIntro('/')).toBe(true)
    globalThis.localStorage.setItem('agriscan_intro_seen_v2', '1')
    expect(shouldPlayIntro('/')).toBe(true)
  })

  it('never plays on the drone camera station', () => {
    // That screen is opened with the aircraft already powered; ten seconds of video
    // between the operator and the capture controls is not acceptable there.
    expect(shouldPlayIntro('/camera')).toBe(false)
  })

  it('is skipped when the person asked for reduced motion', () => {
    globalThis.window = fakeWindow({ reducedMotion: true })
    expect(shouldPlayIntro('/')).toBe(false)
  })

  it('survives storage being unavailable', () => {
    // Private browsing throws on access. The intro still plays; only the sound
    // preference is lost.
    globalThis.localStorage = {
      getItem() { throw new Error('denied') },
      setItem() { throw new Error('denied') },
    }
    expect(shouldPlayIntro('/')).toBe(true)
    // Unreadable storage must not be mistaken for "they turned sound off".
    expect(soundWanted()).toBe(true)
  })

  it('wants sound by default, and remembers being silenced', () => {
    expect(soundWanted()).toBe(true)
    globalThis.localStorage.setItem('agriscan_intro_sound', 'off')
    expect(soundWanted()).toBe(false)
    globalThis.localStorage.setItem('agriscan_intro_sound', 'on')
    expect(soundWanted()).toBe(true)
  })
})

describe('guided tour', () => {
  const roles = ['farmer', 'technician', 'admin', 'researcher']

  it('walks an admin through every dashboard page', () => {
    const paths = tourForRole('admin').map((s) => s.path)
    for (const required of ['/', '/map', '/detections', '/verify', '/recommendations',
      '/drone-camera', '/captures', '/missions', '/aircraft', '/upload', '/field-boundaries',
      '/fields', '/farmers', '/analytics', '/models', '/users', '/account']) {
      expect(paths, `admin tour missing ${required}`).toContain(required)
    }
  })

  it('never walks a role into a page that would refuse them', () => {
    // These are the role lists App.jsx enforces on the routes themselves.
    const guarded = {
      '/users': ['admin'],
      '/drone-camera': ['admin', 'technician'],
      '/verify': ['admin', 'technician', 'researcher'],
      '/recommendations': ['admin', 'technician', 'researcher'],
      '/upload': ['admin', 'technician', 'researcher'],
      '/analytics': ['admin', 'technician', 'researcher'],
      '/farmers': ['admin', 'technician', 'researcher'],
    }
    for (const role of ['technician', 'researcher', 'admin']) {
      for (const step of tourForRole(role)) {
        const allowed = guarded[step.path]
        if (allowed) expect(allowed, `${role} sent to ${step.path}`).toContain(role)
      }
    }
  })

  it('keeps the farmer inside the field client', () => {
    const steps = tourForRole('farmer')
    expect(steps.length).toBeGreaterThan(0)
    expect(steps.every((s) => s.path.startsWith('/field'))).toBe(true)
    // The farmer's interface is bilingual, so its headings come from the label table.
    for (const step of steps) {
      expect(step.label, `farmer step on ${step.path} needs a label`).toBeTruthy()
      expect(L[step.label], `missing label ${step.label}`).toBeTruthy()
      expect(L[step.label].hil).toBeTruthy()
    }
  })

  it('gives every step a path, a heading and a body', () => {
    for (const role of roles) {
      for (const step of tourForRole(role)) {
        expect(step.path, `${role} step path`).toMatch(/^\//)
        expect(step.title || step.label, `${role} step heading`).toBeTruthy()
        expect(step.body.length, `${role} ${step.path} body`).toBeGreaterThan(40)
      }
    }
  })

  it('writes no HTML entities into plain strings', () => {
    // These are JavaScript strings, not JSX: an entity there renders literally.
    for (const role of roles) {
      for (const step of tourForRole(role)) {
        expect(step.title || '').not.toMatch(/&[a-z]+;/i)
        expect(step.body).not.toMatch(/&[a-z]+;/i)
      }
    }
  })

  it('anchors every step to a navigation control, not to page content', () => {
    // Sidebar links, the account chip and the field tab bar are the only elements that
    // cannot be renamed or moved without the route changing too.
    const allowed = /^(\.as-navlink\[href=|\.as-userchip$|\.fc-tab\[href=|\.fc-account-link$)/
    for (const role of roles) {
      for (const step of tourForRole(role)) {
        expect(step.anchor, `${role} ${step.path} has no anchor`).toBeTruthy()
        expect(step.anchor, `${role} ${step.path} anchor`).toMatch(allowed)
      }
    }
  })

  it('points each step at the control that opens its own page', () => {
    for (const role of roles) {
      for (const step of tourForRole(role)) {
        const href = step.anchor.match(/href="([^"]+)"/)
        if (href) expect(href[1], `${step.path} points elsewhere`).toBe(step.path)
      }
    }
  })

  it('times each step by how much there is to read', () => {
    for (const role of roles) {
      for (const step of tourForRole(role)) {
        const ms = stepDuration(step)
        // Never a flash, never a stall: long enough to read a short step, capped so a
        // long one cannot hold someone who stopped paying attention.
        expect(ms, `${step.path} too short`).toBeGreaterThanOrEqual(7000)
        expect(ms, `${step.path} too long`).toBeLessThanOrEqual(20000)
      }
    }
    const short = stepDuration({ title: 'A', body: 'Two words.' })
    const long = stepDuration({ title: 'A', body: 'word '.repeat(40) })
    expect(long).toBeGreaterThan(short)
  })

  it('visits each page only once', () => {
    for (const role of roles) {
      const paths = tourForRole(role).map((s) => s.path)
      expect(new Set(paths).size, `${role} repeats a page`).toBe(paths.length)
    }
  })
})
