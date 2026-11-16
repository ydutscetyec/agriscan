import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { STATUS } from './Detection'

/** Shared filter panel. The Map and Detections pages use the same object shape so a
 *  filter set carries between them unchanged. */
export const EMPTY_FILTERS = {
  field_id: '',
  condition: '',
  status: '',
  min_confidence: '',
  min_severity: '',
  date_from: '',
  date_to: '',
  source: '',
}

export function toQuery(filters, extra = {}) {
  const params = { include_demo: 'true', limit: '500', ...extra }
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined && key !== 'min_severity') {
      params[key] = value
    }
  })
  return params
}

/** Severity has no server-side filter yet, so it is applied in the browser and the
 *  UI says so rather than pretending the server did it. */
export function applySeverityFilter(rows, filters) {
  if (!filters.min_severity) return rows
  const min = Number(filters.min_severity)
  return rows.filter((row) => (row.severity ?? -1) >= min)
}

export default function Filters({ value, onChange, layout = 'grid' }) {
  const [fields, setFields] = useState([])
  const [conditions, setConditions] = useState([])

  useEffect(() => {
    api.fields().then(setFields).catch(() => setFields([]))
    api.conditions().then(setConditions).catch(() => setConditions([]))
  }, [])

  const set = (key) => (event) => onChange({ ...value, [key]: event.target.value })

  return (
    <div className={layout === 'grid' ? 'as-filters' : ''}>
      <div className="as-field">
        <label className="as-label" htmlFor="f-field">Field</label>
        <select id="f-field" className="as-select" value={value.field_id} onChange={set('field_id')}>
          <option value="">All fields</option>
          {fields.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-cond">Condition</label>
        <select id="f-cond" className="as-select" value={value.condition} onChange={set('condition')}>
          <option value="">All conditions</option>
          {conditions.map((c) => (
            <option key={c.code} value={c.code}>{c.common_name}</option>
          ))}
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-status">Verification status</label>
        <select id="f-status" className="as-select" value={value.status} onChange={set('status')}>
          <option value="">Any status</option>
          {Object.entries(STATUS).map(([key, s]) => (
            <option key={key} value={key}>{s.label}</option>
          ))}
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-source">Image source</label>
        <select id="f-source" className="as-select" value={value.source} onChange={set('source')}>
          <option value="">Drone and phone</option>
          <option value="phone">Phone (close range)</option>
          <option value="drone">Drone (zone level)</option>
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-from">Captured from</label>
        <input id="f-from" type="date" className="as-input" value={value.date_from} onChange={set('date_from')} />
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-to">Captured to</label>
        <input id="f-to" type="date" className="as-input" value={value.date_to} onChange={set('date_to')} />
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-conf">Minimum model confidence</label>
        <select id="f-conf" className="as-select" value={value.min_confidence} onChange={set('min_confidence')}>
          <option value="">Any confidence</option>
          <option value="0.5">50% and above</option>
          <option value="0.7">70% and above</option>
          <option value="0.9">90% and above</option>
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="f-sev">Minimum severity</label>
        <select id="f-sev" className="as-select" value={value.min_severity} onChange={set('min_severity')}>
          <option value="">Any severity</option>
          <option value="10">Moderate and above (10%)</option>
          <option value="30">Severe (30%)</option>
        </select>
      </div>
    </div>
  )
}
