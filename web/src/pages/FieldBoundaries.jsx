import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapContainer, Polygon, Tooltip, useMap } from 'react-leaflet'
import { MapPin, MapPinned, PencilRuler } from 'lucide-react'
import { api } from '../api/client'
import { BaseTiles, FIT_MAX_ZOOM, useBaseMap } from '../components/BaseMap'
import { EmptyState, FieldShape, PageHeader } from '../components/Layout'

const DEFAULT_CENTER = [6.3711, 124.7461]

/** GeoJSON is [lon, lat]; Leaflet wants [lat, lon]. Converted in exactly one place. */
function toPositions(geojson) {
  const geometry = geojson?.type === 'Feature' ? geojson.geometry : geojson
  if (!geometry || geometry.type !== 'Polygon') return []
  return (geometry.coordinates?.[0] || []).map(([lon, lat]) => [lat, lon])
}

function MapController({ fields, selectedId }) {
  const map = useMap()
  const fitted = useRef(false)

  // Fit to every drawn field once, on first load.
  useEffect(() => {
    if (fitted.current) return
    const all = fields.flatMap((f) => toPositions(f.boundary_geojson))
    if (all.length) {
      map.fitBounds(all, { padding: [30, 30], maxZoom: FIT_MAX_ZOOM })
      fitted.current = true
    }
  }, [fields, map])

  // Then follow the selection.
  useEffect(() => {
    if (!selectedId) return
    const field = fields.find((f) => f.id === selectedId)
    const positions = field ? toPositions(field.boundary_geojson) : []
    if (positions.length) map.flyToBounds(positions, { padding: [60, 60], duration: 0.6, maxZoom: FIT_MAX_ZOOM })
  }, [selectedId, fields, map])

  return null
}

function stageText(stage) {
  if (!stage || stage.growth_stage === 'DATA_REQUIRED') return 'Planting date not set'
  const words = {
    not_planted: 'Not yet planted', vegetative: 'Vegetative', reproductive: 'Reproductive',
    ripening: 'Ripening', post_harvest: 'Past harvest',
  }
  const word = words[stage.growth_stage] || stage.growth_stage
  return stage.days_after_planting !== null ? `${word}, day ${stage.days_after_planting}` : word
}

export default function FieldBoundaries() {
  const [fields, setFields] = useState(null)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState(null)
  const [baseMap] = useBaseMap()

  useEffect(() => {
    api.fieldsSummary()
      .then((rows) => setFields(Array.isArray(rows) ? rows : []))
      .catch((err) => { setError(err.message); setFields([]) })
  }, [])

  const drawn = useMemo(
    () => (fields || []).filter((f) => toPositions(f.boundary_geojson).length > 2),
    [fields],
  )
  const undrawn = useMemo(
    () => (fields || []).filter((f) => toPositions(f.boundary_geojson).length <= 2),
    [fields],
  )
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? drawn.filter((f) => f.name.toLowerCase().includes(q)) : drawn
  }, [drawn, query])

  const totalArea = drawn.reduce((n, f) => n + (f.area_ha || 0), 0)

  if (fields === null) {
    return <div className="as-content"><p className="as-muted">Loading fields…</p></div>
  }

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Fields"
        icon={MapPin}
        title="Field boundaries"
        description={
          drawn.length
            ? `${drawn.length} field${drawn.length === 1 ? '' : 's'} mapped, ${totalArea.toFixed(2)} ha in total. Select one to see it on the map.`
            : 'Every field with a drawn boundary, shown together on one map.'
        }
        actions={
          <Link className="as-btn secondary" to="/fields">
            <PencilRuler size={16} strokeWidth={1.75} /> Draw or edit a field
          </Link>
        }
      />

      {error && <div className="as-warn" style={{ marginBottom: 16 }}>{error}</div>}

      {drawn.length === 0 ? (
        <EmptyState
          icon={MapPinned}
          title="No field boundaries yet"
          action={<Link className="as-btn" to="/fields">Draw a field</Link>}
        >
          Draw a field's boundary on the Manage fields page and it appears here, with its
          area, growth stage and detection counts.
        </EmptyState>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 360px) 1fr', gap: 16, alignItems: 'start' }}>
          <div>
            <input
              className="as-input"
              placeholder="Find a field"
              aria-label="Find a field by name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ marginBottom: 10, background: '#fff' }}
            />
            <div style={{ display: 'grid', gap: 8, maxHeight: '68vh', overflowY: 'auto', paddingRight: 2 }}>
              {visible.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`as-fieldcard${selectedId === f.id ? ' selected' : ''}`}
                  onClick={() => setSelectedId(f.id)}
                  aria-pressed={selectedId === f.id}
                >
                  <FieldShape geojson={f.boundary_geojson} />
                  <div style={{ minWidth: 0 }}>
                    <div className="as-fieldcard-name">{f.name}</div>
                    <div className="as-fieldcard-meta">
                      {f.area_ha ? `${f.area_ha.toFixed(2)} ha` : 'Area not set'}
                      {f.variety ? `, ${f.variety}` : ''}
                    </div>
                    <div className="as-fieldcard-meta">{stageText(f.growth_stage)}</div>
                    <div className="as-fieldcard-stats">
                      <span>{f.images} image{f.images === 1 ? '' : 's'}</span>
                      <span>{f.detections_verified} of {f.detections_total} verified</span>
                    </div>
                  </div>
                </button>
              ))}
              {visible.length === 0 && (
                <p className="as-muted" style={{ fontSize: 13 }}>No field matches “{query}”.</p>
              )}
            </div>

            {undrawn.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <h3>Boundary not drawn</h3>
                <p className="as-muted" style={{ fontSize: 12.5, marginTop: 0 }}>
                  These fields exist but have no boundary, so they cannot be placed on the map.
                </p>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                  {undrawn.map((f) => <li key={f.id}>{f.name}</li>)}
                </ul>
                <Link to="/fields" style={{ fontSize: 13 }}>Draw them on Manage fields</Link>
              </div>
            )}
          </div>

          <div className="as-card plain" style={{ padding: 0, overflow: 'hidden', height: '72vh', position: 'sticky', top: 16 }}>
            <MapContainer center={DEFAULT_CENTER} zoom={14} scrollWheelZoom>
              <BaseTiles layer={baseMap} />
              <MapController fields={drawn} selectedId={selectedId} />
              {drawn.map((f) => {
                const selected = selectedId === f.id
                return (
                  <Polygon
                    key={f.id}
                    positions={toPositions(f.boundary_geojson)}
                    pathOptions={{
                      color: selected ? '#202532' : '#648B2F',
                      weight: selected ? 3 : 2,
                      fillColor: '#8BAF3F',
                      fillOpacity: selected ? 0.35 : 0.15,
                    }}
                    eventHandlers={{ click: () => setSelectedId(f.id) }}
                  >
                    <Tooltip sticky>
                      <strong>{f.name}</strong>
                      <br />
                      {f.area_ha ? `${f.area_ha.toFixed(2)} ha` : 'Area not set'}
                    </Tooltip>
                  </Polygon>
                )
              })}
            </MapContainer>
          </div>
        </div>
      )}
    </div>
  )
}
