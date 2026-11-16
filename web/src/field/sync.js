/**
 * Upload queue.
 *
 * Drains oldest-first. Every attempt sends the same clientUuid, so a retry after a
 * half-completed upload returns the existing record rather than creating a second one.
 * A capture is marked synced only when the server hands back an image id.
 */

import { STATE, markSynced, pendingCaptures, updateCapture } from './db'

export const BASE_DELAY_MS = 2000
export const MAX_DELAY_MS = 5 * 60 * 1000
export const MAX_ATTEMPTS = 8

/** Exponential backoff, capped. Deterministic so it can be tested. */
export function backoffDelay(attempts, base = BASE_DELAY_MS, max = MAX_DELAY_MS) {
  return Math.min(base * 2 ** Math.max(0, attempts - 1), max)
}

/**
 * Upload one capture.
 * `uploader` is injected so this is testable without a network.
 */
export async function uploadOne(capture, uploader, { idb, now = Date.now } = {}) {
  await updateCapture(capture.clientUuid, { state: STATE.UPLOADING }, idb)

  try {
    const result = await uploader({
      clientUuid: capture.clientUuid,
      blob: capture.blob,
      fieldId: capture.fieldId,
      source: capture.source,
      zoneRef: capture.zoneRef,
      note: capture.note,
      meta: capture.meta,
    })

    const imageId = result && (result.image_id ?? result.imageId)
    if (!imageId) {
      // No record id means we cannot prove the server kept it. Keep the local copy.
      throw new Error('Server did not return a record id.')
    }
    return await markSynced(capture.clientUuid, imageId, idb)
  } catch (error) {
    const attempts = (capture.attempts || 0) + 1
    const patch = {
      state: STATE.FAILED,
      attempts,
      lastError: String(error.message || error),
      nextAttemptAt: now() + backoffDelay(attempts),
    }
    if (attempts >= MAX_ATTEMPTS) {
      patch.nextAttemptAt = now() + MAX_DELAY_MS
    }
    return updateCapture(capture.clientUuid, patch, idb)
  }
}

/** Drain everything currently due. Returns a small summary. */
export async function drainQueue(uploader, { idb, now = Date.now } = {}) {
  const due = await pendingCaptures(idb, now())
  let uploaded = 0
  let failed = 0

  for (const capture of due) {
    const result = await uploadOne(capture, uploader, { idb, now })
    if (result && result.state === STATE.SYNCED) uploaded += 1
    else failed += 1
  }
  return { attempted: due.length, uploaded, failed }
}

/**
 * Wire the queue to the browser: drain on reconnect and on a timer.
 * Returns a stop function.
 */
export function startSync(uploader, { intervalMs = 15000, onChange } = {}) {
  let running = false

  async function run() {
    if (running || (typeof navigator !== 'undefined' && navigator.onLine === false)) return
    running = true
    try {
      const summary = await drainQueue(uploader)
      if (onChange && summary.attempted > 0) onChange(summary)
    } catch {
      // A drain failure is not fatal: the queue is still on disk and we try again.
    } finally {
      running = false
    }
  }

  const timer = setInterval(run, intervalMs)
  if (typeof window !== 'undefined') window.addEventListener('online', run)
  run()

  return function stop() {
    clearInterval(timer)
    if (typeof window !== 'undefined') window.removeEventListener('online', run)
  }
}
