import { useEffect, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { api } from '../api/client'
import { PageHeader } from '../components/Layout'

/* Counts are facts and always shown. Precision, recall and F1 are claims, and the server
   withholds them below the minimum sample size — this page never computes its own. */

function pct(value) {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

function cellShade(count, rowTotal, diagonal) {
  if (!count || !rowTotal) return 'transparent'
  const share = count / rowTotal
  // Diagonal (correct) in green, off-diagonal (errors) in amber. Strength = share of row.
  return diagonal
    ? `rgba(139, 175, 63, ${0.12 + share * 0.55})`
    : `rgba(201, 138, 30, ${0.1 + share * 0.5})`
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [agreement, setAgreement] = useState(null)
  const [includeDemo, setIncludeDemo] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = includeDemo ? { include_demo: 'true' } : {}
    Promise.all([
      api.confusionMatrix(params),
      api.agreement(params).catch(() => null),
    ])
      .then(([matrix, agree]) => {
        setData(matrix)
        setAgreement(agree)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [includeDemo])

  const labels = data?.labels || []
  const matrix = data?.matrix || {}

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Analysis"
        icon={BarChart3} title="Analytics" description="Model predictions against technician-verified labels, built directly from the database on every load. Nothing on this page is stored or hand-entered." />

      <label className="as-check" style={{ margin: '12px 0 20px' }}>
        <input type="checkbox" checked={includeDemo}
               onChange={(e) => setIncludeDemo(e.target.checked)} />
        <span style={{ fontSize: 13 }}>Include demo records</span>
      </label>

      {includeDemo && (
        <div className="as-warn" style={{ marginBottom: 16 }}>
          Demo records are included. Nothing shown here may be reported as a result.
        </div>
      )}

      {loading && <p className="as-muted">Calculating metrics…</p>}
      {error && <div className="as-warn">{error}</div>}

      {data && !loading && (
        <>
          <div className="as-grid cols-4" style={{ marginBottom: 20 }}>
            <div className="as-card">
              <div className="as-stat-value">{data.verified_pairs}</div>
              <div className="as-stat-label">Verified pairs</div>
              <div className="as-stat-filter">
                Prediction and technician label both recorded
              </div>
            </div>
            <div className="as-card">
              <div className="as-stat-value">{data.min_required}</div>
              <div className="as-stat-label">Needed for metrics</div>
              <div className="as-stat-filter">Minimum before any figure is shown</div>
            </div>
            <div className="as-card">
              <div className="as-stat-value">{data.cannot_determine}</div>
              <div className="as-stat-label">Could not determine</div>
              <div className="as-stat-filter">Excluded from the matrix</div>
            </div>
            <div className="as-card">
              <div className="as-stat-value">
                {data.sufficient ? pct(data.overall_accuracy) : '—'}
              </div>
              <div className="as-stat-label">Agreement on reviewed set</div>
              <div className="as-stat-filter">
                {data.sufficient ? 'See the sampling note below' : 'Withheld'}
              </div>
            </div>
          </div>

          {!data.sufficient && (
            <div className="as-warn" style={{ marginBottom: 20 }}>
              <strong>{data.metrics_message}</strong>
              <div style={{ marginTop: 4 }}>
                {data.verified_pairs} of {data.min_required} verified pairs so far.
                Counts are shown below; precision, recall and F1 appear once the minimum
                is reached.
              </div>
            </div>
          )}

          <div className="as-section" style={{ marginBottom: 20 }}>
            <h2>Confusion matrix</h2>
            <p className="as-stat-filter" style={{ marginTop: 0 }}>
              Rows: what the model predicted. Columns: what the technician verified.
              The diagonal is agreement.
            </p>

            {labels.length === 0 ? (
              <div className="as-empty">
                No verified detections yet. The matrix fills as technicians clear the
                verification queue.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="as-table" style={{ width: 'auto' }}>
                  <thead>
                    <tr>
                      <th>Predicted ↓ / Verified →</th>
                      {labels.map((label) => <th key={label}>{label}</th>)}
                      <th>Row total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labels.map((row) => {
                      const rowData = matrix[row] || {}
                      const rowTotal = Object.values(rowData).reduce((a, b) => a + b, 0)
                      return (
                        <tr key={row}>
                          <th style={{ textAlign: 'left' }}>{row}</th>
                          {labels.map((col) => {
                            const count = rowData[col] || 0
                            return (
                              <td
                                key={col}
                                style={{
                                  textAlign: 'center',
                                  background: cellShade(count, rowTotal, row === col),
                                  fontWeight: row === col ? 700 : 400,
                                }}
                                title={`${count} predicted ${row}, verified ${col}`}
                              >
                                {count || ''}
                              </td>
                            )
                          })}
                          <td style={{ textAlign: 'center' }} className="as-muted">
                            {rowTotal}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="as-section" style={{ marginBottom: 20 }}>
            <h2>Per-class metrics</h2>
            {labels.length === 0 ? (
              <div className="as-empty">No classes to report yet.</div>
            ) : (
              <table className="as-table">
                <thead>
                  <tr>
                    <th>Class</th>
                    <th>Predicted</th>
                    <th>Verified</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>F1</th>
                  </tr>
                </thead>
                <tbody>
                  {labels.map((label) => {
                    const stats = data.per_class[label] || {}
                    return (
                      <tr key={label}>
                        <td style={{ fontWeight: 600 }}>{label}</td>
                        <td>{stats.support_predicted ?? 0}</td>
                        <td>{stats.support_verified ?? 0}</td>
                        <td>{pct(stats.precision)}</td>
                        <td>{pct(stats.recall)}</td>
                        <td>{pct(stats.f1)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {agreement && (
            <div className="as-section" style={{ marginBottom: 20 }}>
              <h2>Agreement</h2>
              <dl className="as-kv">
                <dt>Model vs technician</dt>
                <dd>
                  {agreement.model_vs_technician?.agreement_rate != null
                    ? pct(agreement.model_vs_technician.agreement_rate)
                    : 'Not enough cases'}
                  <span className="as-muted">
                    {' '}· {agreement.model_vs_technician?.decided_cases ?? 0} decided
                  </span>
                </dd>
                <dt>Farmer vs technician</dt>
                <dd>
                  {agreement.farmer_vs_technician?.agreement_rate != null
                    ? pct(agreement.farmer_vs_technician.agreement_rate)
                    : 'Not enough cases'}
                  <span className="as-muted">
                    {' '}· {agreement.farmer_vs_technician?.paired_cases ?? 0} paired
                  </span>
                </dd>
              </dl>
            </div>
          )}

          <div className="as-note">
            <strong>Read this before quoting any figure.</strong> {data.sampling_note}
          </div>
        </>
      )}
    </div>
  )
}
