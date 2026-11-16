import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { api } from '../../api/client'
import { Bi, L } from '../labels'

/* Six answers, in this order, nothing else. A farmer decides what to do from this
   screen; anything extra on it competes with the decision. */
function Answer({ k, children }) {
  return (
    <div className="fc-answer">
      <div className="fc-answer-label"><Bi k={k} /></div>
      <div className="fc-answer-value">{children}</div>
    </div>
  )
}

const SEVERITY_WORDS = {
  none: 'None', mild: 'Mild', moderate: 'Moderate', severe: 'Severe',
}

function severityWord(value) {
  if (value === null || value === undefined) return 'Not measured'
  if (value <= 0.5) return SEVERITY_WORDS.none
  if (value < 10) return SEVERITY_WORDS.mild
  if (value < 30) return SEVERITY_WORDS.moderate
  return SEVERITY_WORDS.severe
}

export default function ResultDetail() {
  const { id } = useParams()
  const [det, setDet] = useState(null)
  const [recs, setRecs] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [thanks, setThanks] = useState(false)

  function load() {
    api.detection(id).then(setDet).catch((err) => setError(err.message))
    api.recommendationsFor(id).then(setRecs).catch(() => setRecs(null))
  }

  useEffect(() => { load() }, [id])

  async function feedback(agrees) {
    setBusy(true)
    try {
      await api.submitFeedback(id, agrees)
      setThanks(true)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="as-warn">{error}</div>
  if (!det) return <p className="as-muted">Loading…</p>

  const approved = (recs?.recommendations || []).find((r) => r.approved)
  const hasUnapproved = (recs?.recommendations || []).length > 0 && !approved
  const alreadyAnswered = det.farmer_feedback.length > 0

  return (
    <div>
      <p style={{ marginTop: 0 }}>
        <Link to="/field/results" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><ChevronLeft size={16} strokeWidth={1.75} /> <Bi k="myResults" /></Link>
      </p>

      <Answer k="what">{det.condition_name}</Answer>

      <Answer k="where">
        {det.field.name}
        {det.image.lat !== null && det.image.lon !== null ? (
          <div style={{ fontSize: 14, fontWeight: 400, color: 'var(--muted)' }}>
            {det.image.lat.toFixed(5)}, {det.image.lon.toFixed(5)}
          </div>
        ) : (
          <div style={{ fontSize: 14, fontWeight: 400, color: 'var(--muted)' }}>
            Position missing.
          </div>
        )}
      </Answer>

      <Answer k="howSevere">
        {severityWord(det.severity)}
        {det.severity !== null && det.severity !== undefined && (
          <span style={{ color: 'var(--muted)' }}> · {det.severity.toFixed(1)}%</span>
        )}
      </Answer>

      <Answer k="howConfident">
        {det.confidence_label}
        <div style={{ fontSize: 13, fontWeight: 400, color: 'var(--muted)' }}>
          This is how sure the computer model is. It is not a certainty, and a technician
          has {det.verifications.length > 0 ? 'checked it' : 'not yet checked it'}.
        </div>
      </Answer>

      <div className="fc-answer">
        <div className="fc-answer-label"><Bi k="whatToDo" /></div>
        {approved ? (
          <div className="fc-answer-value plain">{approved.text}</div>
        ) : (
          <div className="as-warn">
            {L.pendingReview.en} · {L.pendingReview.hil}
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {hasUnapproved
                ? 'Advice for this case is written but a technician has not signed it yet.'
                : 'No advice has been prepared for this case yet.'}
            </div>
          </div>
        )}
      </div>

      <Answer k="whenToCall">
        <div className="fc-answer-value plain">
          Call your municipal agricultural technician before applying any treatment, and
          straight away if the affected area is spreading.
        </div>
      </Answer>

      <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '24px 0' }} />

      <div className="fc-answer-label" style={{ marginBottom: 8 }}>
        <Bi k="isThisRight" />
      </div>
      <p className="as-muted" style={{ fontSize: 13, marginTop: 0 }}>
        You are telling us whether the computer got it right. You are not approving the
        advice — only a technician does that.
      </p>

      {alreadyAnswered || thanks ? (
        <div className="as-note">
          Thank you. Your answer was recorded and a technician will see it.
        </div>
      ) : (
        <div className="fc-feedback">
          <button className="as-btn" disabled={busy} onClick={() => feedback(true)}>
            {L.yes.en} · {L.yes.hil}
          </button>
          <button className="as-btn secondary" disabled={busy} onClick={() => feedback(false)}>
            {L.no.en} · {L.no.hil}
          </button>
        </div>
      )}
    </div>
  )
}
