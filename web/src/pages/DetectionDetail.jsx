import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { api } from '../api/client'
import { useAuthedImage } from '../hooks/useAuthedImage'
import { useAuth } from '../state/auth'
import { ConfidenceLabel, SeverityTag, StatusBadge, statusOf } from '../components/Detection'

/** Boxes are in source-image pixels; the <img> is scaled. Overlay coordinates are
 *  recomputed from the rendered size so they stay on the lesion at any width. */
function BoxOverlay({ bbox, natural, rendered }) {
  if (!bbox || !natural.w || !rendered.w) return null
  const boxes = Array.isArray(bbox[0]) ? bbox : [bbox]
  const scaleX = rendered.w / natural.w
  const scaleY = rendered.h / natural.h
  return boxes.map((box, index) => {
    const [x1, y1, x2, y2] = box
    return (
      <span
        key={index}
        className="as-bbox"
        style={{
          left: x1 * scaleX,
          top: y1 * scaleY,
          width: (x2 - x1) * scaleX,
          height: (y2 - y1) * scaleY,
        }}
      />
    )
  })
}

function Row({ label, children }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  )
}

export default function DetectionDetail() {
  const { id } = useParams()
  const { user, can } = useAuth()
  const [det, setDet] = useState(null)
  const [recs, setRecs] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [natural, setNatural] = useState({ w: 0, h: 0 })
  const [rendered, setRendered] = useState({ w: 0, h: 0 })
  const imgRef = useRef(null)

  const reload = () => {
    api.detection(id).then(setDet).catch((err) => setError(err.message))
    api.recommendationsFor(id).then(setRecs).catch(() => setRecs(null))
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  async function sendFeedback(agrees) {
    setBusy(true)
    setActionError(null)
    try {
      await api.submitFeedback(id, agrees)
      reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function generate() {
    setBusy(true)
    setActionError(null)
    try {
      await api.generateRecommendation(id)
      reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const { src: imageSrc, failed: imageFailed } = useAuthedImage(det?.image?.id)

  useEffect(() => {
    function measure() {
      if (imgRef.current) {
        setRendered({ w: imgRef.current.clientWidth, h: imgRef.current.clientHeight })
      }
    }
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  if (error) return <div className="as-content"><div className="as-warn">{error}</div></div>
  if (!det) return <div className="as-content"><p className="as-muted">Loading…</p></div>

  const status = statusOf(det.verification_status)
  const reviewed = det.verifications.length > 0

  return (
    <div className="as-content">
      <p style={{ marginTop: 0 }}>
        <Link to="/detections" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><ChevronLeft size={16} strokeWidth={1.75} /> All detections</Link>
      </p>
      <h1>{det.condition_name}</h1>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 6 }}>
        <StatusBadge status={det.verification_status} />
        <ConfidenceLabel label={det.confidence_label} />
        <SeverityTag value={det.severity} method={det.severity_method} />
      </div>
      <p className="as-muted" style={{ fontSize: 12.5, marginTop: 0 }}>{status.note}</p>

      <div className="as-grid cols-2" style={{ alignItems: 'start' }}>
        <div className="as-card plain">
          <h2>Image</h2>
          {imageFailed ? (
            <div className="as-empty">
              Image file is not available on this server.
            </div>
          ) : !imageSrc ? (
            <div className="as-empty">Loading image…</div>
          ) : (
            <div className="as-detimage">
              <img
                ref={imgRef}
                src={imageSrc}
                alt={`Capture showing ${det.condition_name}`}
                onLoad={(e) => {
                  setNatural({ w: e.target.naturalWidth, h: e.target.naturalHeight })
                  setRendered({ w: e.target.clientWidth, h: e.target.clientHeight })
                }}
              />
              <BoxOverlay bbox={det.bbox} natural={natural} rendered={rendered} />
            </div>
          )}
          <p className="as-muted" style={{ fontSize: 12 }}>
            {det.image.source === 'drone'
              ? 'Aerial frame. A drone image may only carry zone-level labels.'
              : 'Close-range phone capture.'}
          </p>
        </div>

        <div className="as-card plain">
          <h2>Record</h2>
          <dl className="as-kv">
            <Row label="Field">{det.field.name}</Row>
            <Row label="Variety">{det.field.variety}</Row>
            <Row label="Captured">
              {(det.image.captured_at || '').replace('T', ' ').slice(0, 16) || 'Not available'}
            </Row>
            <Row label="Position">
              {det.image.lat !== null && det.image.lon !== null
                ? `${det.image.lat.toFixed(5)}, ${det.image.lon.toFixed(5)} (${det.image.gps_source})`
                : 'Position missing.'}
            </Row>
            <Row label="Growth stage">
              {det.growth_stage.growth_stage}
              {det.growth_stage.days_after_planting !== null && (
                <span className="as-muted">
                  {' '}· {det.growth_stage.days_after_planting} days after planting ·
                  rule {det.growth_stage.rule_version}
                </span>
              )}
            </Row>
            <Row label="Image quality">{det.image.quality_flag}</Row>
            <Row label="Uploaded by">{det.image.uploaded_by}</Row>
            <Row label="Model version">{det.model_version}</Row>
            <Row label="Processing version">
              {det.processing_version ? (
                <>
                  {det.processing_version.pipeline_version}{' '}
                  <span className="as-muted">
                    · settings {det.processing_version.config_hash}
                  </span>
                </>
              ) : (
                <span className="as-muted">
                  Not recorded. Made before processing versions were tracked.
                </span>
              )}
            </Row>
            <Row label="Architecture">{det.model_architecture}</Row>
            <Row label="Dataset version">{det.model_dataset_version}</Row>
            <Row label="Severity method">
              {det.severity_method}{' '}
              <span className="as-muted">({det.severity_status})</span>
            </Row>
          </dl>

          <div className="as-warn" style={{ marginTop: 12 }}>{det.severity_note}</div>
          {det.is_demo && (
            <div className="as-warn" style={{ marginTop: 8 }}>
              Demo record. Excluded from research metrics.
            </div>
          )}
        </div>
      </div>

      <div className="as-grid cols-2" style={{ marginTop: 16, alignItems: 'start' }}>
        <div className="as-card plain">
          <h2>Technician review</h2>
          {!reviewed ? (
            <div className="as-empty">
              No technician has reviewed this detection yet.
            </div>
          ) : (
            <table className="as-table">
              <thead>
                <tr><th>Decision</th><th>Technician</th><th>Corrected to</th><th>Severity</th><th>When</th></tr>
              </thead>
              <tbody>
                {det.verifications.map((v) => (
                  <tr key={v.id}>
                    <td style={{ fontWeight: 600 }}>{v.decision}</td>
                    <td>{v.technician}</td>
                    <td>{v.corrected_condition || '—'}</td>
                    <td>{v.severity_score ?? '—'}</td>
                    <td className="as-muted">{(v.verified_at || '').replace('T', ' ').slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {det.verifications.some((v) => v.notes) && (
            <ul style={{ fontSize: 13, paddingLeft: 18 }}>
              {det.verifications.filter((v) => v.notes).map((v) => (
                <li key={`n-${v.id}`}>{v.notes}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="as-card plain">
          <h2>Farmer feedback</h2>
          {user?.role === 'farmer' && det.farmer_feedback.length === 0 && (
            <div style={{ marginBottom: 12 }}>
              <p style={{ fontSize: 13, marginTop: 0 }}>
                Does this match what you see in the field?
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="as-btn" disabled={busy} onClick={() => sendFeedback(true)}>
                  Yes, that looks right
                </button>
                <button className="as-btn secondary" disabled={busy}
                        onClick={() => sendFeedback(false)}>
                  No, that is not what I see
                </button>
              </div>
              {actionError && <div className="as-warn" style={{ marginTop: 10 }}>{actionError}</div>}
            </div>
          )}
          {det.farmer_feedback.length === 0 ? (
            <div className="as-empty">No farmer has responded to this detection yet.</div>
          ) : (
            <table className="as-table">
              <thead><tr><th>Farmer</th><th>Response</th><th>Comment</th><th>When</th></tr></thead>
              <tbody>
                {det.farmer_feedback.map((f) => (
                  <tr key={f.id}>
                    <td>{f.user}</td>
                    <td style={{ fontWeight: 600 }}>{f.agrees ? 'Agrees' : 'Disagrees'}</td>
                    <td>{f.comment || '—'}</td>
                    <td className="as-muted">{(f.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="as-muted" style={{ fontSize: 12 }}>
            Farmer feedback is evidence about a detection. It is not a verified label.
          </p>
        </div>
      </div>

      <div className="as-card plain" style={{ marginTop: 16 }}>
        <h2>What to do</h2>
        {!recs || recs.recommendations.length === 0 ? (
          <div className="as-empty">
            <p>No recommendation yet.</p>
            {can('admin', 'technician', 'researcher') && (
              <>
                <p style={{ fontSize: 13 }}>
                  {det.verification_status === 'technician_verified'
                    ? 'Generate one from the knowledge base, then approve it.'
                    : 'Recommendations are generated only after a technician verifies the detection.'}
                </p>
                <button className="as-btn" disabled={busy || det.verification_status !== 'technician_verified'}
                        onClick={generate}>
                  Generate recommendation
                </button>
              </>
            )}
            {actionError && <div className="as-warn" style={{ marginTop: 10 }}>{actionError}</div>}
          </div>
        ) : (
          recs.recommendations.map((rec) => (
            <div key={rec.id} style={{ marginBottom: 12 }}>
              {rec.approved ? (
                <>
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{rec.text}</div>
                  {Array.isArray(rec.source_refs) && rec.source_refs.length > 0 && (
                    <p className="as-muted" style={{ fontSize: 12 }}>
                      Sources: {rec.source_refs.map((s) => s.title).join(' · ')}
                    </p>
                  )}
                </>
              ) : (
                <div className="as-warn">
                  {rec.message || 'Pending technician review.'}
                  {rec.text && can('admin', 'technician', 'researcher') && (
                    <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 13 }}>
                      <strong>Draft (not visible to the farmer):</strong>
                      <div>{rec.text}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
