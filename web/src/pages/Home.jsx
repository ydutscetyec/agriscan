import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarElement, CategoryScale, Chart as ChartJS, Legend,
  LineElement, LinearScale, PointElement, Tooltip,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'
import { Camera, Map as MapIcon, ScanSearch, Upload } from 'lucide-react'
import { api } from '../api/client'
import { STATUS } from '../components/Detection'
import { EmptyState } from '../components/Layout'
import { Ring, ReadinessRow, Section } from '../components/Gauge'

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend)

const GREEN = '#8BAF3F'
const NAVY = '#202532'

// From Chapter 3. A class below any of these is reported as untrained.
const MIN_SAMPLES = 150
const MIN_FIELDS = 3
const MIN_DATES = 2

export default function Home() {
  const [rows, setRows] = useState(null)
  const [fields, setFields] = useState([])
  const [conditions, setConditions] = useState([])
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const [error, setError] = useState(null)
  const [pipelineError, setPipelineError] = useState(null)

  useEffect(() => {
    api.detections({ include_demo: 'true', limit: '500' })
      .then((d) => setRows(d.detections))
      .catch((err) => { setError(err.message); setRows([]) })
    api.fieldsSummary()
      .then((d) => setFields(Array.isArray(d) ? d : []))
      .catch((err) => { setPipelineError(err.message); setFields([]) })
    api.conditions().then((c) => setConditions(Array.isArray(c) ? c : [])).catch(() => setConditions([]))
  }, [])

  const pipeline = useMemo(() => ({
    images: fields.reduce((n, f) => n + (f.images || 0), 0),
    detections: fields.reduce((n, f) => n + (f.detections_total || 0), 0),
    awaiting: fields.reduce((n, f) => n + (f.detections_unverified || 0), 0),
    verified: fields.reduce((n, f) => n + (f.detections_verified || 0), 0),
  }), [fields])

  /* Dataset readiness, computed from the verified detections themselves.
     This is the figure that decides which classes can be reported at all, and
     until now it only existed inside a script nobody runs. */
  const readiness = useMemo(() => {
    const verified = (rows || []).filter((r) => r.verification_status === 'technician_verified')
    const byClass = new Map()
    for (const r of verified) {
      const key = r.condition_name || 'Unknown'
      if (!byClass.has(key)) byClass.set(key, { n: 0, fields: new Set(), dates: new Set() })
      const e = byClass.get(key)
      e.n += 1
      if (r.field_id != null) e.fields.add(r.field_id)
      if (r.created_at) e.dates.add(r.created_at.slice(0, 10))
    }
    const names = conditions.length
      ? conditions.map((c) => c.name || c.code)
      : [...byClass.keys()]
    return names.map((name) => {
      const e = byClass.get(name) || { n: 0, fields: new Set(), dates: new Set() }
      return {
        name,
        verified: e.n,
        fields: e.fields.size,
        dates: e.dates.size,
        ok: e.n >= MIN_SAMPLES && e.fields.size >= MIN_FIELDS && e.dates.size >= MIN_DATES,
      }
    }).sort((a, b) => b.verified - a.verified)
  }, [rows, conditions])

  const trainable = readiness.filter((r) => r.ok).length

  const shown = useMemo(() => {
    if (!rows) return []
    return verifiedOnly ? rows.filter((r) => r.verification_status === 'technician_verified') : rows
  }, [rows, verifiedOnly])

  const counts = useMemo(() => {
    const out = {}
    Object.keys(STATUS).forEach((k) => { out[k] = 0 })
    ;(rows || []).forEach((r) => { out[r.verification_status] = (out[r.verification_status] || 0) + 1 })
    return out
  }, [rows])

  const overTime = useMemo(() => {
    const byDay = {}
    shown.forEach((r) => {
      const day = (r.created_at || '').slice(0, 10)
      if (day) byDay[day] = (byDay[day] || 0) + 1
    })
    const labels = Object.keys(byDay).sort()
    return { labels, data: labels.map((d) => byDay[d]) }
  }, [shown])

  const byCondition = useMemo(() => {
    const tally = {}
    shown.forEach((r) => { tally[r.condition_name] = (tally[r.condition_name] || 0) + 1 })
    const labels = Object.keys(tally).sort((a, b) => tally[b] - tally[a])
    return { labels, data: labels.map((l) => tally[l]) }
  }, [shown])

  if (!rows) return <div className="as-content"><p className="as-muted">Loading records…</p></div>

  return (
    <div className="as-content">
      <header className="as-hero">
        <div className="as-hero-eyebrow">Surallah, South Cotabato · wet season</div>
        <h1>Field monitoring</h1>
        <p>
          Where every image stands on the path from capture to a technician-verified
          result. Nothing reaches a farmer as advice until it has passed the last step.
        </p>
        <div className="as-hero-rings">
          <Link className="as-ringlink" to="/upload">
            <Ring tone="dark" value={pipeline.images} total={pipeline.images || 1}
                  label="Images captured" sub="Drone and phone" />
          </Link>
          <Link className="as-ringlink" to="/detections">
            <Ring tone="dark" value={pipeline.detections} total={pipeline.images || 1}
                  label="Model detections" sub="Model output only" />
          </Link>
          <Link className="as-ringlink" to="/verify">
            <Ring tone="dark" value={pipeline.awaiting} total={pipeline.detections || 1}
                  label="Awaiting review" sub="No technician yet" />
          </Link>
          <Link className="as-ringlink" to="/detections">
            <Ring tone="dark" value={pipeline.verified} total={pipeline.detections || 1}
                  label="Technician verified" sub="Usable as ground truth" />
          </Link>
        </div>
      </header>

      {pipelineError && (
        <div className="as-warn" style={{ marginBottom: 20 }}>
          <strong>The capture summary is unavailable.</strong>
          <div style={{ marginTop: 4 }}>
            {pipelineError} — check the backend window for the traceback. The rings above
            read zero because of this, not because nothing was captured.
          </div>
        </div>
      )}
      {error && (
        <div className="as-warn" style={{ marginBottom: 20 }}>
          Detections could not be loaded: {error}
        </div>
      )}

      <nav className="as-quickactions" aria-label="Quick actions">
        <Link to="/drone-camera">
          <Camera size={20} strokeWidth={1.8} />
          <span><strong>Start a capture session</strong>Drone phone, on the ground</span>
        </Link>
        <Link to="/upload">
          <Upload size={20} strokeWidth={1.8} />
          <span><strong>Upload images</strong>From this computer</span>
        </Link>
        <Link to="/map">
          <MapIcon size={20} strokeWidth={1.8} />
          <span><strong>Open the map</strong>Fields and detections</span>
        </Link>
      </nav>

      {readiness.length > 0 && (
        <Section
          eyebrow="Dataset"
          title="Readiness by class"
          note={`A class can be trained and reported only with ${MIN_SAMPLES} verified samples, from at least ${MIN_FIELDS} fields, across at least ${MIN_DATES} visit dates. Anything short of all three is reported as untrained rather than trained badly.`}
          badge={`${trainable}/${readiness.length}`}
          badgeLabel="trainable"
        >
          <div className="as-ready">
            {readiness.map((r) => (
              <ReadinessRow key={r.name} name={r.name} verified={r.verified}
                            fields={r.fields} dates={r.dates} minSamples={MIN_SAMPLES} />
            ))}
          </div>
        </Section>
      )}

      {rows.length === 0 ? (
        <EmptyState
          icon={ScanSearch}
          title="No detections yet"
          action={<Link className="as-btn" to="/upload">Upload images</Link>}
        >
          Detections appear once images are uploaded and the worker has processed them.
          Upload from this computer, or run a drone camera session.
        </EmptyState>
      ) : (
        <>
          <Section
            eyebrow="Verification"
            title="Where detections stand"
            note="Counts by status, demo records included."
          >
            <div className="as-grid cols-4">
              {Object.entries(STATUS).map(([key, s]) => (
                <div className="as-kpi" key={key} style={{ borderLeftColor: s.stroke }}>
                  <div className="as-kpi-value">{counts[key] || 0}</div>
                  <div className="as-kpi-label">{s.label}</div>
                  <div className="as-kpi-note">{s.note}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section
            eyebrow="Trends"
            title="Detections over time and by condition"
            note={verifiedOnly
              ? 'Showing technician-verified detections only.'
              : 'Including unverified model output that no person has checked.'}
          >
            <label className="as-check" style={{ marginBottom: 16 }}>
              <input type="checkbox" checked={verifiedOnly}
                     onChange={(e) => setVerifiedOnly(e.target.checked)} />
              <span style={{ fontSize: 13 }}>Verified detections only</span>
            </label>

            <div className="as-grid cols-2">
              <div>
                <Line
                  data={{
                    labels: overTime.labels,
                    datasets: [{
                      label: 'Detections', data: overTime.data,
                      borderColor: GREEN, backgroundColor: GREEN, tension: 0.25, pointRadius: 3,
                    }],
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                  }}
                />
              </div>
              <div>
                <Bar
                  data={{
                    labels: byCondition.labels,
                    datasets: [{ label: 'Detections', data: byCondition.data, backgroundColor: NAVY }],
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                  }}
                />
              </div>
            </div>
          </Section>
        </>
      )}
    </div>
  )
}
