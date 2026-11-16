import { useEffect, useState } from 'react'
import { Sprout } from 'lucide-react'
import { BaseTiles, useBaseMap } from '../components/BaseMap'
import { MapContainer, Polygon, TileLayer, useMapEvents } from 'react-leaflet'
import { api } from '../api/client'
import { useAuth } from '../state/auth'
import { PageHeader } from '../components/Layout'

const DEFAULT_CENTER = [6.3711, 124.7461]

/** Click to drop a vertex, double-click to close the ring. Deliberately hand-rolled:
 *  a draw plugin is a large dependency for one polygon per field. */
const SAME_POINT = 1e-6 // degrees, about 0.1 m

function dedupe(points) {
  return points.filter((p, i) => i === 0 ||
    Math.abs(p[0] - points[i - 1][0]) > SAME_POINT ||
    Math.abs(p[1] - points[i - 1][1]) > SAME_POINT)
}

function DrawPolygon({ points, setPoints, closed, onClose }) {
  useMapEvents({
    click(event) {
      // Once the ring is closed, a stray click must not quietly add a corner.
      if (closed) return
      setPoints((current) => [...current, [event.latlng.lat, event.latlng.lng]])
    },
    dblclick() {
      if (closed) return
      // A double-click arrives as click, click, dblclick: the two clicks just added
      // the same spot twice. Collapse those before closing.
      setPoints((current) => dedupe(current))
      onClose()
    },
  })
  return points.length > 1 ? (
    <Polygon positions={points} pathOptions={{ color: '#648B2F', weight: 2, dashArray: '4 4' }} />
  ) : null
}

function positionsToGeoJSON(points) {
  if (points.length < 3) return null
  const ring = points.map(([lat, lon]) => [lon, lat])
  ring.push(ring[0])
  return { type: 'Polygon', coordinates: [ring] }
}

function geojsonToPositions(geojson, { open = false } = {}) {
  const geometry = geojson?.type === 'Feature' ? geojson.geometry : geojson
  if (!geometry || geometry.type !== 'Polygon') return []
  const ring = (geometry.coordinates?.[0] || []).map(([lon, lat]) => [lat, lon])
  // GeoJSON closes a ring by repeating its first corner. For editing we want the open
  // list, or every re-save appends one more duplicate corner.
  if (open && ring.length > 1) {
    const [a, b] = [ring[0], ring[ring.length - 1]]
    if (Math.abs(a[0] - b[0]) < SAME_POINT && Math.abs(a[1] - b[1]) < SAME_POINT) ring.pop()
  }
  return ring
}

/** Spherical polygon area, in hectares. Computed here so the number shown matches the
 *  shape drawn; the server keeps whatever value is submitted. */
function areaHectares(points) {
  if (points.length < 3) return null
  const R = 6378137
  const rad = (deg) => (deg * Math.PI) / 180
  let total = 0
  for (let i = 0; i < points.length; i += 1) {
    const [lat1, lon1] = points[i]
    const [lat2, lon2] = points[(i + 1) % points.length]
    total += (rad(lon2) - rad(lon1)) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)))
  }
  return Math.abs((total * R * R) / 2) / 10000
}

export default function Fields() {
  const [baseMap] = useBaseMap()
  const { can } = useAuth()
  const [fields, setFields] = useState([])
  const [farms, setFarms] = useState([])
  const [points, setPoints] = useState([])
  const [closed, setClosed] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ farm_id: '', name: '', variety: '', planting_date: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [deleting, setDeleting] = useState(null)

  const reload = () => api.fields().then(setFields).catch((e) => setError(e.message))
  useEffect(() => {
    reload()
    api.farms().then(setFarms).catch(() => setFarms([]))
  }, [])

  const area = areaHectares(points)

  function startEdit(field) {
    setEditing(field.id)
    setForm({
      farm_id: String(field.farm_id),
      name: field.name,
      variety: field.variety || '',
      planting_date: field.planting_date || '',
    })
    const loaded = geojsonToPositions(field.boundary_geojson, { open: true })
    setPoints(loaded)
    setClosed(loaded.length >= 3)
  }

  function reset() {
    setEditing(null)
    setForm({ farm_id: '', name: '', variety: '', planting_date: '' })
    setPoints([])
    setClosed(false)
  }

  async function removeBoundary(field) {
    const ok = window.confirm(
      `Remove the boundary from "${field.name}"? The field and its records stay; only the ` +
      'shape on the map is removed. You can draw a new one afterwards.',
    )
    if (!ok) return
    setError(null)
    try {
      await api.updateField(field.id, { boundary_geojson: null, area_ha: null })
      if (editing === field.id) { setPoints([]); setClosed(false) }
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  function undoCorner() {
    setPoints((current) => current.slice(0, -1))
    setClosed(false)
  }

  async function remove(field) {
    const ok = window.confirm(
      `Delete "${field.name}"? This cannot be undone.\n\n` +
      'A field with images or flights recorded cannot be deleted, to protect research data.',
    )
    if (!ok) return
    setDeleting(field.id)
    setError(null)
    try {
      await api.deleteField(field.id)
      if (editing === field.id) reset()
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(null)
    }
  }

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setError(null)
    setBusy(true)
    const body = {
      ...form,
      farm_id: Number(form.farm_id),
      boundary_geojson: positionsToGeoJSON(points),
      area_ha: area ? Number(area.toFixed(4)) : null,
      planting_date: form.planting_date || null,
    }
    try {
      if (editing) await api.updateField(editing, body)
      else await api.createField(body)
      reset()
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
        eyebrow="Fields"
        icon={Sprout} title="Manage fields" description="Add fields, draw their boundaries, and set planting dates so growth stage can be worked out." />

      {can('admin', 'technician', 'researcher') && (
        <div className="as-grid cols-2" style={{ marginBottom: 24, alignItems: 'start' }}>
          <form className="as-card plain" onSubmit={submit}>
            <h2>{editing ? 'Edit field' : 'Add a field'}</h2>
            <div className="as-field">
              <label className="as-label" htmlFor="f-farm">Farm</label>
              <select id="f-farm" className="as-select" required value={form.farm_id}
                      onChange={(e) => setForm({ ...form, farm_id: e.target.value })}>
                <option value="">Select a farm</option>
                {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="f-name">Field name</label>
              <input id="f-name" className="as-input" required value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="f-var">Rice variety</label>
              <input id="f-var" className="as-input" value={form.variety}
                     onChange={(e) => setForm({ ...form, variety: e.target.value })} />
            </div>
            <div className="as-field">
              <label className="as-label" htmlFor="f-plant">Planting date</label>
              <input id="f-plant" type="date" className="as-input" value={form.planting_date}
                     onChange={(e) => setForm({ ...form, planting_date: e.target.value })} />
              <p className="as-muted" style={{ fontSize: 12 }}>
                Growth stage is derived from this date. Without it, every observation on
                this field reads DATA_REQUIRED.
              </p>
            </div>
            <div className="as-field">
              <span className="as-label">Boundary</span>
              <p style={{ fontSize: 12.5, margin: '0 0 6px' }}>
                {points.length === 0
                  ? 'Click the map to place the first corner.'
                  : closed
                  ? `Closed ring, ${points.length} corners${area ? ` · ${area.toFixed(2)} ha` : ''}.${
                      area > 20 ? ' That is far larger than a rice parcel — zoom in and redraw.' : ''}`
                  : `${points.length} corner${points.length === 1 ? '' : 's'}. Double-click the map to close the ring.`}
              </p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="as-btn secondary" disabled={!points.length}
                        onClick={undoCorner}>
                  Undo last corner
                </button>
                <button type="button" className="as-btn secondary" disabled={!points.length}
                        onClick={() => { setPoints([]); setClosed(false) }}>
                  Clear boundary
                </button>
              </div>
              {editing && points.length === 0 && (
                <p className="as-muted" style={{ fontSize: 12, margin: '6px 0 0' }}>
                  The saved boundary will be removed when you press Save changes.
                </p>
              )}
            </div>
            {error && <div className="as-warn" style={{ marginBottom: 12 }}>{error}</div>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="as-btn" disabled={busy}>
                {busy ? 'Saving…' : editing ? 'Save changes' : 'Add field'}
              </button>
              {editing && (
                <button type="button" className="as-btn secondary" onClick={reset}>Cancel</button>
              )}
            </div>
          </form>

          <div className="as-card plain" style={{ padding: 0, overflow: 'hidden', height: 420 }}>
            <MapContainer center={DEFAULT_CENTER} zoom={14} doubleClickZoom={false}>
              <BaseTiles layer={baseMap} />
              <DrawPolygon points={points} setPoints={setPoints} closed={closed}
                           onClose={() => setClosed(true)} />
              {fields.map((f) => {
                // The field being edited is drawn by the editor, not from its saved copy.
                // Drawing both was why "Clear boundary" appeared to do nothing.
                if (f.id === editing) return null
                const positions = geojsonToPositions(f.boundary_geojson)
                return positions.length > 2 ? (
                  <Polygon key={f.id} positions={positions}
                           pathOptions={{ color: '#8BAF3F', weight: 2, fillOpacity: 0.08 }}
                           eventHandlers={{ click: (e) => { e.originalEvent?.stopPropagation?.(); if (!points.length) startEdit(f) } }} />
                ) : null
              })}
            </MapContainer>
          </div>
        </div>
      )}

      {fields.length === 0 ? (
        <div className="as-empty">No fields yet. Add one to start monitoring.</div>
      ) : (
        <table className="as-table">
          <thead>
            <tr><th>Field</th><th>Variety</th><th>Planted</th><th>Area</th><th>Boundary</th><th /></tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.id}>
                <td>{f.name}</td>
                <td>{f.variety || <span className="as-muted">DATA_REQUIRED</span>}</td>
                <td>{f.planting_date || <span className="as-muted">DATA_REQUIRED</span>}</td>
                <td>
                  {f.area_ha ? `${f.area_ha.toFixed(2)} ha` : '—'}
                  {f.area_ha > 20 && (
                    <span style={{ color: 'var(--sev-moderate)', fontSize: 12 }}
                          title="Rice parcels here are typically 0.5–1.5 ha. Check the boundary.">
                      {' '}· check boundary
                    </span>
                  )}
                </td>
                <td>{f.boundary_geojson ? 'Drawn' : <span className="as-muted">Not drawn</span>}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {can('admin', 'technician', 'researcher') && (
                    <button className="as-btn secondary" onClick={() => startEdit(f)}>Edit</button>
                  )}
                  {can('admin', 'technician', 'researcher') && f.boundary_geojson && (
                    <button className="as-btn secondary" style={{ marginLeft: 6 }}
                            onClick={() => removeBoundary(f)}>
                      Remove boundary
                    </button>
                  )}
                  {can('admin') && (
                    <button
                      className="as-btn secondary"
                      style={{ marginLeft: 6, color: 'var(--sev-severe)' }}
                      disabled={deleting === f.id}
                      onClick={() => remove(f)}
                    >
                      {deleting === f.id ? 'Deleting…' : 'Delete'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
