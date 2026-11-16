/**
 * Local capture store.
 *
 * A capture lives here from the moment the shutter closes until the server confirms a
 * record id. Nothing is deleted before that confirmation: a farmer standing in a paddy
 * with no signal has exactly one copy of that photograph, and it is this one.
 */

const DB_NAME = 'agriscan-field'
const DB_VERSION = 2
/* Flight video, written while recording so a disconnect, a crash or a reload mid-flight
   does not lose the footage. One record per session. */
const VIDEO_STORE = 'videos'
const STORE = 'captures'

export const STATE = {
  QUEUED: 'queued',
  UPLOADING: 'uploading',
  SYNCED: 'synced',
  FAILED: 'failed',
}

let dbPromise = null

export function openDb(indexedDBImpl) {
  const idb = indexedDBImpl || (typeof indexedDB !== 'undefined' ? indexedDB : null)
  if (!idb) return Promise.reject(new Error('IndexedDB is not available in this browser.'))
  if (dbPromise) return dbPromise

  dbPromise = new Promise((resolve, reject) => {
    const request = idb.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'clientUuid' })
        store.createIndex('by_state', 'state')
        store.createIndex('by_created', 'createdAt')
      }
      // Added in version 2. Existing phones keep their queued captures; the upgrade
      // only adds this store.
      if (!db.objectStoreNames.contains(VIDEO_STORE)) {
        db.createObjectStore(VIDEO_STORE, { keyPath: 'sessionId' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  return dbPromise
}

/** Close the connection and drop the cache. A held-open connection blocks
 *  deleteDatabase, which is how a test suite silently shares state between cases. */
export async function closeDb() {
  if (!dbPromise) return
  try {
    const db = await dbPromise
    db.close()
  } catch {
    // Already closed or never opened.
  }
  dbPromise = null
}

/** Empty the store. Used by tests; deleting the whole database is unreliable while
 *  any connection is open, which silently leaks state between cases. */
export async function clearAll(idb) {
  const db = await openDb(idb)
  await wrap(tx(db, 'readwrite').clear())
}

/** Test seam: drop the cached connection without closing it. */
export function _resetDb() {
  dbPromise = null
}

function tx(db, mode) {
  return db.transaction(STORE, mode).objectStore(STORE)
}

function wrap(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export function newClientUuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  // Fallback for older mobile browsers. Collision risk is irrelevant at this scale,
  // and the server's content hash catches a collision anyway.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0
    const v = ch === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export async function addCapture({ blob, fieldId, source = 'phone', zoneRef, note, meta, idb }) {
  const db = await openDb(idb)
  const record = {
    clientUuid: newClientUuid(),
    blob,
    fieldId,
    source,
    zoneRef: zoneRef || null,
    note: note || null,
    // Drone-camera frames carry their session, device GPS and capture time here.
    // Browser camera frames have no EXIF GPS, so this is the position of record.
    meta: meta || null,
    state: STATE.QUEUED,
    attempts: 0,
    nextAttemptAt: 0,
    lastError: null,
    serverImageId: null,
    createdAt: Date.now(),
  }
  await wrap(tx(db, 'readwrite').add(record))
  return record
}

export async function allCaptures(idb) {
  const db = await openDb(idb)
  const rows = await wrap(tx(db, 'readonly').getAll())
  return rows.sort((a, b) => b.createdAt - a.createdAt)
}

export async function pendingCaptures(idb, now = Date.now()) {
  const rows = await allCaptures(idb)
  return rows
    .filter(
      (r) =>
        (r.state === STATE.QUEUED || r.state === STATE.FAILED) &&
        (r.nextAttemptAt || 0) <= now,
    )
    .sort((a, b) => a.createdAt - b.createdAt) // oldest first
}

export async function getCapture(clientUuid, idb) {
  const db = await openDb(idb)
  return wrap(tx(db, 'readonly').get(clientUuid))
}

export async function updateCapture(clientUuid, patch, idb) {
  const db = await openDb(idb)
  const store = tx(db, 'readwrite')
  const existing = await wrap(store.get(clientUuid))
  if (!existing) return null
  const merged = { ...existing, ...patch }
  await wrap(tx(db, 'readwrite').put(merged))
  return merged
}

/** Only ever called after the server has returned a record id. */
export async function markSynced(clientUuid, serverImageId, idb) {
  if (!serverImageId) throw new Error('Refusing to mark synced without a server record id.')
  return updateCapture(
    clientUuid,
    { state: STATE.SYNCED, serverImageId, lastError: null, nextAttemptAt: 0 },
    idb,
  )
}

export async function countByState(idb) {
  const rows = await allCaptures(idb)
  return rows.reduce((acc, row) => {
    acc[row.state] = (acc[row.state] || 0) + 1
    return acc
  }, {})
}


/* ----------------------------------------------------------------- flight video */

function videoTx(db, mode) {
  return db.transaction(VIDEO_STORE, mode).objectStore(VIDEO_STORE)
}

/** Write what has been recorded so far. Called periodically during a flight, so the
 *  worst a crash costs is the seconds since the last write rather than the whole clip. */
export async function saveVideo(sessionId, blob, seconds, idb) {
  const db = await openDb(idb)
  await wrap(videoTx(db, 'readwrite').put({
    sessionId, blob, seconds, savedAt: Date.now(), type: blob.type,
  }))
}

/** Any flight video still on this phone, newest first. */
export async function pendingVideos(idb) {
  const db = await openDb(idb)
  const all = await wrap(videoTx(db, 'readonly').getAll())
  return all.sort((a, b) => b.savedAt - a.savedAt)
}

export async function dropVideo(sessionId, idb) {
  const db = await openDb(idb)
  await wrap(videoTx(db, 'readwrite').delete(sessionId))
}
