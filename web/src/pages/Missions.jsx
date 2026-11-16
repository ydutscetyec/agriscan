import { useEffect, useState } from 'react'
import { Plane } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../state/auth'
import { PageHeader } from '../components/Layout'

export default function Missions() {
  const { can } = useAuth()
  const [missions, setMissions] = useState([])
  const [fields, setFields] = useState([])
  const [form, setForm] = useState({
    field_id: '', flown_at: '', altitude_m: '', pattern: 'lawnmower',
    weather: '', wind_ms: '', aborted: false, abort_reason: '', notes: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const reload = () => api.missions().then(setMissions).catch((e) => setError(e.message))
  useEffect(() => {
    reload()
    api.fields().then(setFields).catch(() => setFields([]))
  }, [])

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createMission({
        ...form,
        field_id: Number(form.field_id),
        altitude_m: form.altitude_m ? Number(form.altitude_m) : null,
        wind_ms: form.wind_ms ? Number(form.wind_ms) : null,
        flown_at: form.flown_at ? `${form.flown_at}:00` : null,
      })
      setForm({ ...form, notes: '', abort_reason: '', aborted: false })
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Capture"
        icon={Plane} title="Flight records" description="Every flight is recorded, including flights that were aborted. Discarded flights are part of an honest reliability figure, so they stay in the record." />

      {can('admin', 'technician', 'researcher') && (
        <form className="as-card plain" onSubmit={submit} style={{ marginBottom: 24 }}>
          <h2>Record a flight</h2>
          <div className="as-filters">
            <div className="as-field">
              <label className="as-label" htmlFor="m-field">Field</label>
              <select id="m-field" className="as-select" required value={form.field_id}
                      onChange={(e) => setForm({ ...form, field_id: e.target.value })}>
                <option value="">Select a field</option>
                {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="m-when">Flown at</label>
              <input id="m-when" type="datetime-local" className="as-input" value={form.flown_at}
                     onChange={(e) => setForm({ ...form, flown_at: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="m-alt">Altitude (m above canopy)</label>
              <input id="m-alt" type="number" step="0.5" className="as-input" value={form.altitude_m}
                     onChange={(e) => setForm({ ...form, altitude_m: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="m-wind">Wind (m/s)</label>
              <input id="m-wind" type="number" step="0.1" className="as-input" value={form.wind_ms}
                     onChange={(e) => setForm({ ...form, wind_ms: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="m-weather">Weather</label>
              <input id="m-weather" className="as-input" value={form.weather}
                     onChange={(e) => setForm({ ...form, weather: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="m-notes">Notes</label>
              <input id="m-notes" className="as-input" value={form.notes}
                     onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
            <input type="checkbox" checked={form.aborted}
                   onChange={(e) => setForm({ ...form, aborted: e.target.checked })} />
            <span>Flight was aborted</span>
          </label>
          {form.aborted && (
            <div className="as-field">
              <label className="as-label" htmlFor="m-reason">Reason for abort</label>
              <input id="m-reason" className="as-input" value={form.abort_reason}
                     onChange={(e) => setForm({ ...form, abort_reason: e.target.value })} />
            </div>
          )}
          {error && <div className="as-warn" style={{ marginBottom: 12 }}>{error}</div>}
          <button className="as-btn" disabled={busy}>Save flight</button>
        </form>
      )}

      {missions.length === 0 ? (
        <div className="as-empty">No flights recorded yet.</div>
      ) : (
        <table className="as-table">
          <thead>
            <tr>
              <th>ID</th><th>Field</th><th>Flown</th><th>Altitude</th>
              <th>Wind</th><th>Weather</th><th>Result</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {missions.map((m) => (
              <tr key={m.id}>
                <td>{m.id}</td>
                <td>{fields.find((f) => f.id === m.field_id)?.name || m.field_id}</td>
                <td className="as-muted">{(m.flown_at || '').replace('T', ' ').slice(0, 16) || '—'}</td>
                <td>{m.altitude_m ?? '—'}{m.altitude_m ? ' m' : ''}</td>
                <td>{m.wind_ms ?? '—'}{m.wind_ms ? ' m/s' : ''}</td>
                <td>{m.weather || '—'}</td>
                <td style={{ color: m.aborted ? 'var(--sev-severe)' : 'var(--sev-none)', fontWeight: 600 }}>
                  {m.aborted ? `Aborted${m.abort_reason ? `: ${m.abort_reason}` : ''}` : 'Completed'}
                </td>
                <td className="as-muted">{m.notes || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
