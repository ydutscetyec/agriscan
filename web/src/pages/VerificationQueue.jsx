import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuthedImage } from '../hooks/useAuthedImage'
import { ConfidenceLabel, SeverityTag, StatusBadge } from '../components/Detection'
import { ClipboardCheck } from 'lucide-react'
import { PageHeader } from '../components/Layout'

/* Keyboard first. A technician clears a batch of these in one sitting, and reaching for
   the mouse between every case is what makes a queue feel like work. */
const KEYS = {
  c: 'correct',
  x: 'corrected',
  u: 'cannot_determine',
}

function BoxOverlay({ bbox, natural, rendered }) {
  if (!bbox || !natural.w || !rendered.w) return null
  const boxes = Array.isArray(bbox[0]) ? bbox : [bbox]
  const sx = rendered.w / natural.w
  const sy = rendered.h / natural.h
  return boxes.map(([x1, y1, x2, y2], i) => (
    <span
      key={i}
      className="as-bbox"
      style={{ left: x1 * sx, top: y1 * sy, width: (x2 - x1) * sx, height: (y2 - y1) * sy }}
    />
  ))
}

export default function VerificationQueue() {
  const [items, setItems] = useState([])
  const [index, setIndex] = useState(0)
  const [conditions, setConditions] = useState([])
  const [corrected, setCorrected] = useState('')
  const [severity, setSeverity] = useState('')
  const [notes, setNotes] = useState('')
  const [meta, setMeta] = useState({ sample_rate: null, confident_min: null })
  const [natural, setNatural] = useState({ w: 0, h: 0 })
  const [rendered, setRendered] = useState({ w: 0, h: 0 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(0)
  const notesRef = useRef(null)

  const current = items[index] || null
  const { src: imageSrc, failed: imageFailed } = useAuthedImage(current?.image_id)

  const load = useCallback(() => {
    api
      .verificationQueue()
      .then((data) => {
        setItems(data.items)
        setMeta({ sample_rate: data.sample_rate, confident_min: data.confident_min })
        setIndex(0)
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    load()
    api.conditions().then(setConditions).catch(() => setConditions([]))
  }, [load])

  useEffect(() => {
    setCorrected('')
    setSeverity('')
    setNotes('')
    setNatural({ w: 0, h: 0 })
  }, [index])

  const submit = useCallback(
    async (decision) => {
      if (!current || busy) return
      if (decision === 'corrected' && !corrected) {
        setError('Choose the correct condition before saving a correction.')
        return
      }
      setBusy(true)
      setError(null)
      try {
        await api.verifyDetection(current.detection_id, {
          decision,
          corrected_condition: decision === 'corrected' ? corrected : undefined,
          severity_score: severity === '' ? undefined : Number(severity),
          notes: notes || undefined,
        })
        setDone((n) => n + 1)
        if (index + 1 >= items.length) load()
        else setIndex((i) => i + 1)
      } catch (err) {
        setError(err.message)
      } finally {
        setBusy(false)
      }
    },
    [current, busy, corrected, severity, notes, index, items.length, load],
  )

  useEffect(() => {
    function onKey(event) {
      if (event.target.tagName === 'TEXTAREA' || event.target.tagName === 'INPUT') {
        if (event.key === 'Escape') event.target.blur()
        return
      }
      const key = event.key.toLowerCase()
      if (KEYS[key]) {
        event.preventDefault()
        submit(KEYS[key])
      } else if (key >= '0' && key <= '3') {
        setSeverity(key)
      } else if (key === 'n') {
        event.preventDefault()
        notesRef.current?.focus()
      } else if (key === 'j' || key === 'arrowright') {
        setIndex((i) => Math.min(i + 1, items.length - 1))
      } else if (key === 'k' || key === 'arrowleft') {
        setIndex((i) => Math.max(i - 1, 0))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [submit, items.length])

  const picker = useMemo(
    () => conditions.filter((c) => c.code !== 'unknown'),
    [conditions],
  )

  if (error && !current) {
    return <div className="as-content"><div className="as-warn">{error}</div></div>
  }

  if (!current) {
    return (
      <div className="as-content">
        <PageHeader
          eyebrow="Monitoring"
          icon={ClipboardCheck}
          title="Verification queue"
          description="Detections a technician has not yet checked. Nothing here has reached a farmer as advice."
        />
        <div className="as-empty">
          <p>The queue is empty.</p>
          <p style={{ fontSize: 13 }}>
            {done > 0 ? `You cleared ${done} this session. ` : ''}
            New cases appear as images are processed.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="as-content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <PageHeader
          eyebrow="Monitoring"
          icon={ClipboardCheck}
          title="Verification queue"
          description="Detections a technician has not yet checked. Nothing here has reached a farmer as advice."
        />
        <div className="as-muted" style={{ fontSize: 13 }}>
          {index + 1} of {items.length} · {done} cleared this session
        </div>
      </div>

      <div className="as-note" style={{ marginBottom: 16 }}>
        <strong>In the queue because:</strong> {current.queue_reason_label}.
        {current.queue_reason === 'confidence_sample' && (
          <span>
            {' '}
            This one the model was confident about. It is sampled at{' '}
            {Math.round((meta.sample_rate || 0) * 100)}% above{' '}
            {Math.round((meta.confident_min || 0) * 100)}% confidence, so confident
            mistakes get found.
          </span>
        )}
      </div>

      <div className="as-grid cols-2" style={{ alignItems: 'start' }}>
        <div className="as-section">
          {imageFailed && <div className="as-empty">Image file is not available.</div>}
          {!imageFailed && !imageSrc && <div className="as-empty">Loading image…</div>}
          <div className="as-detimage" style={{ display: imageSrc ? 'inline-block' : 'none' }}>
            <img
              src={imageSrc || undefined}
              alt={`Capture under review, model says ${current.condition_name}`}
              onLoad={(e) => {
                setNatural({ w: e.target.naturalWidth, h: e.target.naturalHeight })
                setRendered({ w: e.target.clientWidth, h: e.target.clientHeight })
              }}
            />
            <BoxOverlay bbox={current.bbox} natural={natural} rendered={rendered} />
          </div>
          <p className="as-muted" style={{ fontSize: 12 }}>
            {current.source === 'drone'
              ? 'Aerial frame — zone-level labels only.'
              : 'Close-range phone capture.'}
          </p>
        </div>

        <div className="as-section">
          <h2>Model says: {current.condition_name}</h2>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
            <StatusBadge status={current.verification_status} />
            <ConfidenceLabel label={current.confidence_label} />
            <SeverityTag value={current.severity} method={current.severity_method} />
          </div>
          <p className="as-muted" style={{ fontSize: 12, marginTop: 0 }}>
            Model {current.model_version}. Severity is an experimental estimate, not a
            measurement.
          </p>

          <div className="as-field">
            <label className="as-label" htmlFor="v-cond">
              If this is wrong, what is it?
            </label>
            <select id="v-cond" className="as-select" value={corrected}
                    onChange={(e) => setCorrected(e.target.value)}>
              <option value="">Select the correct condition…</option>
              {picker.map((c) => (
                <option key={c.code} value={c.code}>{c.common_name}</option>
              ))}
            </select>
          </div>

          <div className="as-field">
            <span className="as-label">Severity you observe (keys 0–3)</span>
            <div style={{ display: 'flex', gap: 6 }}>
              {[
                ['0', 'None'], ['1', 'Mild'], ['2', 'Moderate'], ['3', 'Severe'],
              ].map(([value, word]) => (
                <button
                  key={value}
                  type="button"
                  className={`as-btn ${severity === value ? '' : 'secondary'}`}
                  onClick={() => setSeverity(value)}
                >
                  {value} {word}
                </button>
              ))}
            </div>
          </div>

          <div className="as-field">
            <label className="as-label" htmlFor="v-notes">Notes (n to focus, Esc to leave)</label>
            <textarea id="v-notes" ref={notesRef} className="as-input" rows={3}
                      value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          {error && <div className="as-warn" style={{ marginBottom: 12 }}>{error}</div>}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="as-btn" disabled={busy} onClick={() => submit('correct')}>
              Correct <span style={{ opacity: 0.75 }}>(c)</span>
            </button>
            <button className="as-btn navy" disabled={busy} onClick={() => submit('corrected')}>
              Corrected <span style={{ opacity: 0.75 }}>(x)</span>
            </button>
            <button className="as-btn secondary" disabled={busy}
                    onClick={() => submit('cannot_determine')}>
              Cannot determine <span style={{ opacity: 0.75 }}>(u)</span>
            </button>
          </div>

          <p className="as-muted" style={{ fontSize: 12, marginTop: 12 }}>
            c correct · x corrected · u cannot determine · 0–3 severity · n notes ·
            j/k move between cases. Your decision is written as a new record; the model's
            original prediction is never overwritten.
          </p>
        </div>
      </div>
    </div>
  )
}
