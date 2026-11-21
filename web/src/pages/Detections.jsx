import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, ScanSearch, SlidersHorizontal, X } from 'lucide-react'
import { api } from '../api/client'
import Filters, { EMPTY_FILTERS, applySeverityFilter, toQuery } from '../components/Filters'
import { ConfidenceLabel, SeverityTag, STATUS, StatusBadge } from '../components/Detection'
import { EmptyState, PageHeader } from '../components/Layout'

const COLUMNS = [
  { key: 'id', label: 'ID' },
  { key: 'condition_name', label: 'Condition' },
  { key: 'verification_status', label: 'Status' },
  { key: 'confidence', label: 'Model confidence' },
  { key: 'severity', label: 'Severity' },
  { key: 'source', label: 'Source' },
  { key: 'created_at', label: 'Detected' },
]

const PAGE_SIZE = 50

/* The views a technician actually opens. Reaching any of them through the filter
   panel took four interactions; here it takes one. */
const PRESETS = [
  { key: 'all', label: 'All', patch: {} },
  { key: 'review', label: 'Awaiting review', patch: { status: 'ai_detected' } },
  { key: 'unsure', label: 'Low confidence', patch: { status: 'low_confidence' } },
  { key: 'verified', label: 'Verified', patch: { status: 'technician_verified' } },
]

function activeCount(filters) {
  return Object.entries(filters).filter(([k, v]) => v !== '' && k !== 'status').length
}

function presetOf(filters) {
  if (activeCount(filters) > 0) return null
  const match = PRESETS.find((p) => (p.patch.status || '') === filters.status)
  return match ? match.key : null
}

export default function Detections() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [rows, setRows] = useState([])
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [grandTotal, setGrandTotal] = useState(null)
  const [sort, setSort] = useState({ key: 'created_at', dir: 'desc' })
  const [advanced, setAdvanced] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // How many detections exist at all, regardless of filters. This is what tells an
  // empty result apart from an empty database, and the old page could not say which.
  useEffect(() => {
    api.detections({ limit: '1' })
      .then((d) => setGrandTotal(d.total ?? d.count ?? 0))
      .catch(() => setGrandTotal(null))
  }, [])

  // A filter change returns to page one; otherwise page 3 of the old result is empty.
  useEffect(() => { setPage(0) }, [filters])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .detections(toQuery(filters, { limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) }))
      .then((data) => {
        setRows(data.detections)
        setTotal(data.total ?? data.count)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [filters, page])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const firstShown = total === 0 ? 0 : page * PAGE_SIZE + 1
  const lastShown = Math.min(total, (page + 1) * PAGE_SIZE)
  const extras = activeCount(filters)
  const current = presetOf(filters)

  const applyPreset = useCallback((preset) => {
    setFilters({ ...EMPTY_FILTERS, ...preset.patch })
    setAdvanced(false)
  }, [])

  const shown = useMemo(() => {
    const filtered = applySeverityFilter(rows, filters)
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      const x = a[sort.key], y = b[sort.key]
      if (x === y) return 0
      if (x === null || x === undefined) return 1
      if (y === null || y === undefined) return -1
      return x > y ? dir : -dir
    })
  }, [rows, sort, filters])

  function toggleSort(key) {
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))
  }

  const databaseIsEmpty = grandTotal === 0

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Monitoring"
        icon={ScanSearch}
        title="Detections"
        description="Every model detection, newest first. Filter to one field and date range to review a survey."
      />

      <div className="as-quickbar">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            className={`as-chip${current === p.key ? ' on' : ''}`}
            aria-pressed={current === p.key}
            onClick={() => applyPreset(p)}
          >
            {p.label}
          </button>
        ))}

        <span className="as-quickbar-spacer" />

        {extras > 0 && (
          <button type="button" className="as-chip" onClick={() => setFilters(EMPTY_FILTERS)}>
            <X size={14} strokeWidth={2} /> Clear filters
          </button>
        )}
        <button
          type="button"
          className={`as-chip${advanced ? ' on' : ''}`}
          aria-expanded={advanced}
          onClick={() => setAdvanced((v) => !v)}
        >
          <SlidersHorizontal size={14} strokeWidth={1.9} /> More filters
          {extras > 0 && <span className="as-filtercount">{extras}</span>}
        </button>
      </div>

      {advanced && (
        <div className="as-card plain" style={{ marginBottom: 16 }}>
          <Filters value={filters} onChange={setFilters} />
        </div>
      )}

      {error && <div className="as-warn">{error}</div>}
      {loading && <p className="as-muted">Loading detections…</p>}

      {!loading && !error && shown.length === 0 && (
        databaseIsEmpty ? (
          <EmptyState
            icon={ScanSearch}
            title="No detections yet"
            action={<Link className="as-btn" to="/upload">Upload images</Link>}
          >
            Nothing has been detected because no images have been processed. Upload images
            from this computer, or run a drone camera session. Detections appear once the
            worker has a production model and something to work on.
          </EmptyState>
        ) : (
          <EmptyState
            icon={ScanSearch}
            title="Nothing matches this view"
            action={
              <button type="button" className="as-btn secondary"
                      onClick={() => setFilters(EMPTY_FILTERS)}>
                Show all detections
              </button>
            }
          >
            {grandTotal
              ? `There are ${grandTotal} detections in total, but none in this view. Widen the date range or clear the status filter.`
              : 'Widen the date range, or clear the status filter.'}
          </EmptyState>
        )
      )}

      {!loading && !error && shown.length > 0 && (
        <>
          <div className="as-resultline">
            <span>
              Showing {firstShown}–{lastShown} of {total}
              {extras > 0 && ` · ${extras} filter${extras === 1 ? '' : 's'} applied`}
              {filters.min_severity && ' · severity filtered within this page'}
            </span>
            <Pager page={page} pageCount={pageCount} setPage={setPage} loading={loading} />
          </div>

          <div className="as-card plain" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="as-table">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className="sortable" onClick={() => toggleSort(c.key)}>
                      {c.label}
                      {sort.key === c.key ? (sort.dir === 'asc' ? ' \u2191' : ' \u2193') : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => {
                  const s = STATUS[d.verification_status]
                  return (
                    /* The whole row opens the detection. It used to be the id cell
                       alone, which is a one-character target on a row that looks
                       clickable, so "I can't click it" was the common reaction. The
                       id stays a real link for middle-click and open-in-new-tab. */
                    <tr key={d.id} className="as-row"
                        style={{ borderLeftColor: s ? s.stroke : 'transparent',
                                 cursor: 'pointer' }}
                        tabIndex={0}
                        role="link"
                        aria-label={`Open detection ${d.id}, ${d.condition_name}`}
                        onClick={() => navigate(`/detections/${d.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            navigate(`/detections/${d.id}`)
                          }
                        }}>
                      <td>
                        <Link to={`/detections/${d.id}`}
                              onClick={(e) => e.stopPropagation()}>{d.id}</Link>
                      </td>
                      <td style={{ fontWeight: 600 }}>{d.condition_name}</td>
                      <td><StatusBadge status={d.verification_status} /></td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {d.confidence !== null && d.confidence !== undefined && (
                          <span className="as-confbar" aria-hidden="true">
                            <span style={{ width: `${Math.round(d.confidence * 100)}%` }} />
                          </span>
                        )}
                        <ConfidenceLabel value={d.confidence} />
                      </td>
                      <td><SeverityTag value={d.severity} method={d.severity_method} /></td>
                      <td>{d.source}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{(d.created_at || '').slice(0, 10)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
            <Pager page={page} pageCount={pageCount} setPage={setPage} loading={loading} />
          </div>
        </>
      )}
    </div>
  )
}

function Pager({ page, pageCount, setPage, loading }) {
  if (pageCount <= 1) return null
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <button className="as-btn secondary" disabled={loading || page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}>
        <ChevronLeft size={16} strokeWidth={1.75} /> Previous
      </button>
      <span style={{ fontSize: 13 }}>Page {page + 1} of {pageCount}</span>
      <button className="as-btn secondary" disabled={loading || page >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}>
        Next <ChevronRight size={16} strokeWidth={1.75} />
      </button>
    </div>
  )
}
