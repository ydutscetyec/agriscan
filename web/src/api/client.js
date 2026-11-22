/** Thin fetch wrapper. The token lives in memory and sessionStorage, never in a cookie
 *  we could leak cross-site, and every call carries it explicitly. */

// Same-origin by default: Vite proxies /api to Flask, in both http and https modes.
// Set VITE_API_BASE only if the API is served from somewhere else entirely.
const BASE = import.meta.env.VITE_API_BASE || '/api'

let token = sessionStorage.getItem('agriscan_token') || null

export function setToken(value) {
  token = value
  if (value) sessionStorage.setItem('agriscan_token', value)
  else sessionStorage.removeItem('agriscan_token')
}

export function getToken() {
  return token
}

/** Small cached JPEG for list views; the server makes it once. */
/** Newest viewfinder frame for a paired phone. Cache-busted by the caller. */
/** The flight video for a session. Range requests make it scrubbable. */
/** Every photo from one session as a zip. Opened directly, so it needs the token in
 *  the query rather than a header — see sessionZipUrl's use. */
export function sessionZipUrl(sessionId) {
  return `${BASE}/capture/sessions/${sessionId}/images.zip`
}

export function flightVideoUrl(sessionId) {
  return `${BASE}/capture/sessions/${sessionId}/video`
}

export function devicePreviewUrl(deviceId) {
  return `${BASE}/capture/devices/${deviceId}/preview`
}

export function imageThumbUrl(imageId) {
  return `${BASE}/images/${imageId}/thumb`
}

export function imageFileUrl(imageId) {
  return `${BASE}/images/${imageId}/file`
}

/**
 * Fetch a protected image and return an object URL for an <img>.
 *
 * A plain <img src> cannot carry the Authorization header, so pointing it straight at
 * the image endpoint always fails with 401. This fetches with the token instead.
 * The caller must URL.revokeObjectURL() the result when done.
 */
export async function fetchImageObjectUrl(imageId, { thumb = false } = {}) {
  const response = await fetch(thumb ? imageThumbUrl(imageId) : imageFileUrl(imageId), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error('Image file is not available on this server.')
  return URL.createObjectURL(await response.blob())
}

/** Multipart POST. Separate from request(), which sends JSON. */
async function requestForm(path, form) {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) throw new Error(`Upload failed (${response.status})`)
  return response.json()
}

export const API_BASE = BASE

/* When the server says a token is no longer valid (expired after 12 h, password changed,
   account deactivated), the app must go back to sign-in instead of showing errors on a
   page that still looks signed in. AuthProvider listens for this. */
const UNAUTHORIZED = 'agriscan:unauthorized'

export function onUnauthorized(handler) {
  window.addEventListener(UNAUTHORIZED, handler)
  return () => window.removeEventListener(UNAUTHORIZED, handler)
}

function sessionEnded() {
  setToken(null)
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(UNAUTHORIZED))
}

// Requests made without a token (sign-in) get the server's own message on 401:
// "Invalid credentials." The old code replaced it with "Your session has ended",
// which is what a farmer saw after mistyping a password.
async function request(path, { method = 'GET', body, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } }
  if (token) opts.headers.Authorization = `Bearer ${token}`
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${BASE}${path}`, opts)
  } catch {
    throw new Error('Cannot reach the AGRISCAN server. Check that the backend is running.')
  }

  const hadToken = Boolean(opts.headers.Authorization)
  if (response.status === 204) return null

  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (response.status === 401) {
    if (hadToken) {
      sessionEnded()
      throw new Error('Your session has ended. Sign in again.')
    }
    throw new Error((data && data.error) || 'Invalid credentials.')
  }
  if (response.status === 502 || response.status === 504) {
    throw new Error('The AGRISCAN server is not answering. It may be restarting; try again in a minute.')
  }
  if (!response.ok) {
    throw new Error((data && data.error) || `Request failed (${response.status}).`)
  }
  return data
}

/**
 * Upload one image and report progress. Uses XMLHttpRequest because fetch() has no
 * upload-progress event. Resolves with the server's JSON; rejects with a readable error.
 */
export function uploadImageWithProgress({ file, fieldId, source, clientUuid }, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    form.append('field_id', String(fieldId))
    form.append('source', source || 'phone')
    if (clientUuid) form.append('client_uuid', clientUuid)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/images`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch { data = null }
      if (xhr.status === 401) {
        sessionEnded()
        reject(new Error('Your session has ended. Sign in again.'))
      } else if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data)
      } else {
        reject(new Error((data && data.error) || `Upload failed (${xhr.status}).`))
      }
    }
    xhr.onerror = () =>
      reject(new Error('Upload failed. Please check your connection and try again.'))
    xhr.send(form)
  })
}

export const api = {
  login: (name, password) => request('/auth/login', { method: 'POST', body: { name, password } }),
  me: () => request('/auth/me'),

  fields: () => request('/fields'),
  field: (id, observationDate) =>
    request(`/fields/${id}${observationDate ? `?observation_date=${observationDate}` : ''}`),
  createField: (body) => request('/fields', { method: 'POST', body }),
  updateField: (id, body) => request(`/fields/${id}`, { method: 'PUT', body }),
  deleteField: (id) => request(`/fields/${id}`, { method: 'DELETE' }),

  farms: () => request('/farms'),
  farmers: () => request('/people/farmers'),

  conditions: () => request('/conditions'),

  detections: (params) => request(`/detections?${new URLSearchParams(params)}`),
  detection: (id) => request(`/detections/${id}`),

  image: (id) => request(`/images/${id}`),
  myCaptures: () => request('/images?mine=true'),
  captures: (limit = 100, sessionId = null) =>
    request(`/images?limit=${limit}${sessionId ? `&capture_session_id=${sessionId}` : ''}`),
  deleteCaptureDevice: (id) => request(`/capture/devices/${id}`, { method: 'DELETE' }),
  deleteCaptureSession: (id) => request(`/capture/sessions/${id}`, { method: 'DELETE' }),
  /* Sent in pieces. Cloudflare's free tier refuses a request body over 100 MB and a
     ten-minute clip is several hundred, which is the 502 a whole-file upload produced.
     Pieces also mean a dropped connection costs one piece, not the entire upload.
     onProgress is called with a fraction so the phone can show how far it has got. */
  uploadFlightVideo: async (id, blob, durationS, onProgress) => {
    const CHUNK = 4 * 1024 * 1024
    let sent = 0
    for (let index = 0; sent < blob.size; index += 1) {
      const piece = blob.slice(sent, Math.min(sent + CHUNK, blob.size))
      const form = new FormData()
      form.append('chunk', piece, 'part')
      form.append('index', String(index))
      form.append('offset', String(sent))
      // One retry per piece: a phone on one bar drops the odd request, and failing the
      // whole upload for that would be the wrong answer after a flight.
      try {
        await requestForm(`/capture/sessions/${id}/video/chunk`, form)
      } catch {
        await requestForm(`/capture/sessions/${id}/video/chunk`, form)
      }
      sent += piece.size
      onProgress?.(sent / blob.size)
    }
    return request(`/capture/sessions/${id}/video/complete`, {
      method: 'POST',
      body: { mime: (blob.type || 'video/webm').split(';')[0], duration_s: durationS || null },
    })
  },
  uploadFlightTrack: (id, points) =>
    request(`/capture/sessions/${id}/track`, { method: 'POST', body: { points } }),
  flightTrack: (id) => request(`/capture/sessions/${id}/track`),
  extractFrames: (id, intervalS) =>
    request(`/capture/sessions/${id}/frames`, {
      method: 'POST', body: { interval_s: intervalS },
    }),
  saveVideoFrame: (sessionId, offsetS, blob) => {
    const form = new FormData()
    form.append('frame', blob, 'frame.jpg')
    form.append('capture_session_id', String(sessionId))
    form.append('offset_s', String(offsetS))
    return requestForm('/images/from-video', form)
  },
  deleteCapture: (id) => request(`/images/${id}`, { method: 'DELETE' }),

  missions: () => request('/missions'),
  createMission: (body) => request('/missions', { method: 'POST', body }),

  models: () => request('/models'),

  // fields overview (boundaries page, overview pipeline)
  fieldsSummary: () => request('/fields-summary'),

  // drone camera: phone side
  registerCaptureDevice: (body) => request('/capture/devices', { method: 'POST', body }),
  pollCaptureDevice: (id, body) => request(`/capture/devices/${id}/poll`, { method: 'POST', body }),
  sendPreviewFrame: (id, blob) => {
    const form = new FormData()
    form.append('frame', blob, 'preview.jpg')
    return requestForm(`/capture/devices/${id}/preview`, form)
  },

  // drone camera: dashboard side
  captureDevices: () => request('/capture/devices'),
  captureSessions: () => request('/capture/sessions'),
  armCaptureSession: (body) => request('/capture/sessions', { method: 'POST', body }),
  stopCaptureSession: (id) => request(`/capture/sessions/${id}/stop`, { method: 'POST' }),

  // mission planner (Track B, pure computation)
  plannerGsd: (altitudeM) => request(`/trackb/planner/gsd?altitude_m=${encodeURIComponent(altitudeM)}`),

  // verification
  verificationQueue: (params = {}) =>
    request(`/verification-queue?${new URLSearchParams(params)}`),
  verifyDetection: (id, body) => request(`/detections/${id}/verify`, { method: 'POST', body }),
  submitFeedback: (id, agrees, comment) =>
    request(`/detections/${id}/feedback`, { method: 'POST', body: { agrees, comment } }),
  confusionMatrix: (params = {}) =>
    request(`/analysis/confusion-matrix?${new URLSearchParams(params)}`),
  agreement: (params = {}) =>
    request(`/analysis/agreement?${new URLSearchParams(params)}`),

  // recommendations
  recommendationsFor: (detectionId) => request(`/recommendations/${detectionId}`),
  generateRecommendation: (detectionId) =>
    request(`/recommendations/${detectionId}/generate`, { method: 'POST' }),
  pendingRecommendations: () => request('/recommendations/pending'),
  approveRecommendation: (id, text) =>
    request(`/recommendations/${id}/approve`, { method: 'POST', body: { text } }),
  rejectRecommendation: (id, reason) =>
    request(`/recommendations/${id}/reject`, { method: 'POST', body: { reason } }),
  users: () => request('/users'),
  createUser: (body) => request('/users', { method: 'POST', body }),
  updateUser: (id, body) => request(`/users/${id}`, { method: 'PUT', body }),
  resetPassword: (id, password) =>
    request(`/users/${id}/password`, { method: 'POST', body: { password } }),

  // own account
  changePassword: (currentPassword, newPassword) =>
    request('/auth/password', {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword },
    }),

  // server and worker status, for the operator banner
  health: () => request('/health'),
}
