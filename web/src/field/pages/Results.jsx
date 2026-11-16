import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { SeverityTag, StatusBadge } from '../../components/Detection'
import { STATE, allCaptures } from '../db'
import { Bi } from '../labels'

/* Two lists merged, newest first: what is still on the phone, and what the server has.
   A farmer should not have to know which is which to find their photo. */
export default function Results({ refreshKey }) {
  const [local, setLocal] = useState([])
  const [remote, setRemote] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    allCaptures().then(setLocal).catch(() => setLocal([]))
    api.myCaptures()
      .then((data) => setRemote(data.captures))
      .catch(() => setError('Cannot reach the server. Showing what is stored on this phone.'))
  }, [refreshKey])

  const syncedIds = new Set(local.filter((c) => c.serverImageId).map((c) => c.serverImageId))
  const waiting = local.filter((c) => c.state !== STATE.SYNCED)

  return (
    <div>
      <h1 style={{ fontSize: 20 }}><Bi k="myResults" /></h1>
      {error && <div className="as-warn" style={{ marginBottom: 12 }}>{error}</div>}

      {waiting.length === 0 && remote.length === 0 && (
        <div className="as-empty">
          <p>No photos yet.</p>
          <p style={{ fontSize: 13 }}>Take one from the first tab.</p>
        </div>
      )}

      {waiting.map((capture) => (
        <div className="fc-item" key={capture.clientUuid}>
          <div className="fc-item-top">
            <span className="fc-item-title">Waiting to send</span>
            <span className="fc-pill offline"><Bi k="queued" /></span>
          </div>
          <p className="as-muted" style={{ fontSize: 13, margin: '6px 0 0' }}>
            Queued — will analyse when connected.
            {capture.attempts > 0 &&
              ` Tried ${capture.attempts} time${capture.attempts === 1 ? '' : 's'}.`}
          </p>
          <p className="as-muted" style={{ fontSize: 12, margin: 0 }}>
            Taken {new Date(capture.createdAt).toLocaleString()}
          </p>
        </div>
      ))}

      {remote.map((capture) => {
        const det = capture.detection
        const justSent = syncedIds.has(capture.image_id)
        return (
          <Link
            className="fc-item"
            key={capture.image_id}
            to={det ? `/field/results/${det.id}` : '#'}
            onClick={(e) => { if (!det) e.preventDefault() }}
          >
            <div className="fc-item-top">
              <span className="fc-item-title">
                {det ? det.condition_name : 'Photo received'}
              </span>
              {justSent && <span className="fc-pill"><Bi k="synced" /></span>}
            </div>

            {det ? (
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
                <StatusBadge status={det.verification_status} />
                <SeverityTag value={det.severity} method={det.severity_method} />
              </div>
            ) : (
              <p className="as-muted" style={{ fontSize: 13, margin: '6px 0 0' }}>
                {capture.quality_flag && capture.quality_flag !== 'ok'
                  ? 'Image rejected — recapture required.'
                  : 'Inference queued.'}
              </p>
            )}

            <p className="as-muted" style={{ fontSize: 12, margin: '6px 0 0' }}>
              {capture.field_name}
              {capture.captured_at
                ? ` · ${capture.captured_at.replace('T', ' ').slice(0, 16)}`
                : ''}
            </p>
          </Link>
        )
      })}
    </div>
  )
}
