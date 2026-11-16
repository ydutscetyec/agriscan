/**
 * Offline queue behaviour. These are the acceptance criteria for Prompt 5, so they run
 * against a real IndexedDB implementation (fake-indexeddb), not a stubbed store.
 */

import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  STATE, addCapture, allCaptures, clearAll, closeDb, countByState, getCapture, markSynced,
  pendingCaptures, _resetDb,
} from '../db'
import { MAX_ATTEMPTS, backoffDelay, drainQueue, uploadOne } from '../sync'

async function freshDb() {
  await clearAll()
}

const blob = () => new Blob(['fake-jpeg-bytes'], { type: 'image/jpeg' })

beforeEach(async () => {
  await freshDb()
})

describe('capture store', () => {
  it('stores a capture with a client uuid and queued state', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    expect(rec.clientUuid).toMatch(/^[0-9a-f-]{36}$/i)
    expect(rec.state).toBe(STATE.QUEUED)
  })

  it('survives a reload: three captures persist and are still queued', async () => {
    await addCapture({ blob: blob(), fieldId: 1 })
    await addCapture({ blob: blob(), fieldId: 1 })
    await addCapture({ blob: blob(), fieldId: 1 })

    _resetDb() // simulates the page being closed and reopened
    const rows = await allCaptures()
    expect(rows).toHaveLength(3)
    expect(rows.every((r) => r.state === STATE.QUEUED)).toBe(true)
  })

  it('refuses to mark synced without a server record id', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    await expect(markSynced(rec.clientUuid, null)).rejects.toThrow(/server record id/i)
  })

  it('drains oldest first', async () => {
    const a = await addCapture({ blob: blob(), fieldId: 1 })
    await new Promise((r) => setTimeout(r, 5))
    const b = await addCapture({ blob: blob(), fieldId: 1 })
    const due = await pendingCaptures()
    expect(due[0].clientUuid).toBe(a.clientUuid)
    expect(due[1].clientUuid).toBe(b.clientUuid)
  })
})

describe('backoff', () => {
  it('grows exponentially and is capped', () => {
    expect(backoffDelay(1, 1000, 60000)).toBe(1000)
    expect(backoffDelay(2, 1000, 60000)).toBe(2000)
    expect(backoffDelay(3, 1000, 60000)).toBe(4000)
    expect(backoffDelay(20, 1000, 60000)).toBe(60000)
  })
})

describe('upload', () => {
  it('marks synced only after a record id comes back', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    const uploader = vi.fn().mockResolvedValue({ image_id: 42 })
    const after = await uploadOne(rec, uploader)
    expect(after.state).toBe(STATE.SYNCED)
    expect(after.serverImageId).toBe(42)
  })

  it('keeps the local copy when the server returns no record id', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    const uploader = vi.fn().mockResolvedValue({})
    const after = await uploadOne(rec, uploader)
    expect(after.state).toBe(STATE.FAILED)
    const stored = await getCapture(rec.clientUuid)
    expect(stored).toBeTruthy()
    expect(stored.blob).toBeTruthy()
  })

  it('schedules a later retry after a failure', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    const uploader = vi.fn().mockRejectedValue(new Error('offline'))
    const after = await uploadOne(rec, uploader, { now: () => 1_000_000 })
    expect(after.state).toBe(STATE.FAILED)
    expect(after.attempts).toBe(1)
    expect(after.nextAttemptAt).toBeGreaterThan(1_000_000)
  })

  it('sends the same clientUuid on every retry, so the server can dedupe', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    const seen = []
    const uploader = vi.fn(async ({ clientUuid }) => {
      seen.push(clientUuid)
      if (seen.length < 3) throw new Error('connection lost')
      return { image_id: 7 }
    })
    for (let i = 0; i < 3; i += 1) {
      const current = await getCapture(rec.clientUuid)
      await uploadOne(current, uploader, { now: () => 0 })
    }
    expect(seen).toHaveLength(3)
    expect(new Set(seen).size).toBe(1)
    const final = await getCapture(rec.clientUuid)
    expect(final.state).toBe(STATE.SYNCED)
  })
})

describe('drainQueue', () => {
  it('uploads three queued captures exactly once each', async () => {
    await addCapture({ blob: blob(), fieldId: 1 })
    await addCapture({ blob: blob(), fieldId: 1 })
    await addCapture({ blob: blob(), fieldId: 1 })

    let nextId = 100
    const calls = []
    const uploader = vi.fn(async ({ clientUuid }) => {
      calls.push(clientUuid)
      return { image_id: nextId++ }
    })

    const summary = await drainQueue(uploader, { now: () => Date.now() })
    expect(summary).toMatchObject({ attempted: 3, uploaded: 3, failed: 0 })
    expect(new Set(calls).size).toBe(3)

    const second = await drainQueue(uploader, { now: () => Date.now() })
    expect(second.attempted).toBe(0)
    expect(uploader).toHaveBeenCalledTimes(3)

    const counts = await countByState()
    expect(counts[STATE.SYNCED]).toBe(3)
  })

  it('does not retry a capture before its backoff expires', async () => {
    await addCapture({ blob: blob(), fieldId: 1 })
    const failing = vi.fn().mockRejectedValue(new Error('offline'))
    await drainQueue(failing, { now: () => 0 })
    expect(failing).toHaveBeenCalledTimes(1)

    await drainQueue(failing, { now: () => 1 })
    expect(failing).toHaveBeenCalledTimes(1)

    await drainQueue(failing, { now: () => 10_000_000 })
    expect(failing).toHaveBeenCalledTimes(2)
  })

  it('gives up scheduling tight retries after MAX_ATTEMPTS', async () => {
    const rec = await addCapture({ blob: blob(), fieldId: 1 })
    const failing = vi.fn().mockRejectedValue(new Error('offline'))
    let current = rec
    for (let i = 0; i < MAX_ATTEMPTS; i += 1) {
      current = await uploadOne(current, failing, { now: () => 0 })
    }
    expect(current.attempts).toBe(MAX_ATTEMPTS)
    const stored = await getCapture(rec.clientUuid)
    expect(stored.blob).toBeTruthy()
  })
})

describe('drone camera metadata', () => {
  it('keeps session id and device GPS through a reload', async () => {
    const meta = {
      captureSessionId: 7, missionId: 3, capturedAt: '2026-10-10T09:15:00.000Z',
      lat: 6.3711, lon: 124.7461, accuracy: 4.2, altitude: 31.5,
    }
    const rec = await addCapture({ blob: blob(), fieldId: 2, source: 'drone', meta })
    _resetDb()
    const stored = await getCapture(rec.clientUuid)
    expect(stored.source).toBe('drone')
    expect(stored.meta).toEqual(meta)
  })

  it('hands the metadata to the uploader on every attempt', async () => {
    const meta = { captureSessionId: 9, lat: 6.37, lon: 124.74, accuracy: 3 }
    const rec = await addCapture({ blob: blob(), fieldId: 2, source: 'drone', meta })
    const uploader = vi.fn().mockResolvedValue({ image_id: 55 })
    await uploadOne(rec, uploader)
    expect(uploader).toHaveBeenCalledWith(expect.objectContaining({ meta, source: 'drone' }))
  })

  it('a frame with no GPS fix is still queued, just without a position', async () => {
    const rec = await addCapture({
      blob: blob(), fieldId: 2, source: 'drone',
      meta: { captureSessionId: 11, capturedAt: '2026-10-10T09:16:00.000Z' },
    })
    const stored = await getCapture(rec.clientUuid)
    expect(stored.state).toBe(STATE.QUEUED)
    expect(stored.meta.lat).toBeUndefined()
  })
})
