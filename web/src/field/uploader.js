/**
 * The one place a queued capture becomes an HTTP request.
 *
 * Both the farmer field client and the drone camera station write to the same on-phone
 * queue, so both drain it through this function. Two uploaders on one queue would race
 * on the same capture.
 */
import { getToken } from '../api/client'

const BASE = import.meta.env.VITE_API_BASE || '/api'

export async function uploadCapture({ clientUuid, blob, fieldId, source, zoneRef, note, meta }) {
  const form = new FormData()
  form.append('file', blob, `${clientUuid}.jpg`)
  form.append('field_id', String(fieldId))
  form.append('source', source || 'phone')
  form.append('client_uuid', clientUuid) // makes a retry idempotent server-side
  if (zoneRef) form.append('zone_ref', zoneRef)
  if (note) form.append('note', note)

  if (meta) {
    if (meta.captureSessionId) form.append('capture_session_id', String(meta.captureSessionId))
    if (meta.missionId) form.append('mission_id', String(meta.missionId))
    if (meta.capturedAt) form.append('captured_at', meta.capturedAt)
    // Device geolocation at the moment of capture. Sent only when there was a fix.
    if (typeof meta.lat === 'number' && typeof meta.lon === 'number') {
      form.append('lat', String(meta.lat))
      form.append('lon', String(meta.lon))
      if (typeof meta.accuracy === 'number') form.append('gps_accuracy_m', String(meta.accuracy))
      if (typeof meta.altitude === 'number') form.append('gps_altitude_m', String(meta.altitude))
    }
  }

  const token = getToken()
  const response = await fetch(`${BASE}/images`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) throw new Error(`Upload rejected (${response.status}).`)
  return response.json()
}
