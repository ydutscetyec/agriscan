import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BaseMapChoice, BaseTiles, useBaseMap } from '../components/BaseMap'
import {
  MapContainer, Marker, Polygon, Popup, TileLayer, useMap, useMapEvents,
} from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import { api } from '../api/client'
import Filters, { EMPTY_FILTERS, applySeverityFilter, toQuery } from '../components/Filters'
import {
  ConfidenceLabel, MapLegend, SeverityTag, StatusBadge, markerIcon,
} from '../components/Detection'

/* Surallah, South Cotabato. Used only until a field boundary exists to fit to. */
const DEFAULT_CENTER = [6.3711, 124.7461]
const CLUSTER_ABOVE = 200

function BoundsWatcher({ onChange }) {
  const map = useMapEvents({
    moveend: () => onChange(map.getBounds()),
    zoomend: () => onChange(map.getBounds()),
  })
  useEffect(() => {
    onChange(map.getBounds())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}

function FitToFields({ polygons }) {
  const map = useMap()
  useEffect(() => {
    if (!polygons.length) return
    const all = polygons.flatMap((p) => p.positions)
    if (all.length) map.fitBounds(all, { padding: [30, 30] })
  }, [polygons, map])
  return null
}

/** GeoJSON stores [lon, lat]; Leaflet wants [lat, lon]. Getting this backwards puts
 *  a Surallah field in the Indian Ocean, so it is converted in exactly one place. */
function geojsonToPositions(geojson) {
  if (!geojson) return []
  const geometry = geojson.type === 'Feature' ? geojson.geometry : geojson
  if (!geometry || geometry.type !== 'Polygon') return []
  const ring = geometry.coordinates?.[0] || []
  return ring.map(([lon, lat]) => [lat, lon])
}

export default function MapPage() {
  const [baseMap, setBaseMap] = useBaseMap()
  const navigate = useNavigate()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [rows, setRows] = useState([])
  const [fields, setFields] = useState([])
  const [bounds, setBounds] = useState(null)
  const [verifiedOnly, setVerifiedOnly] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.fields().then(setFields).catch(() => setFields([]))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const extra = {}
      if (bounds) {
        extra.min_lat = bounds.getSouth()
        extra.max_lat = bounds.getNorth()
        extra.min_lon = bounds.getWest()
        extra.max_lon = bounds.getEast()
      }
      const data = await api.detections(toQuery(filters, extra))
      setRows(data.detections)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filters, bounds])

  useEffect(() => {
    load()
  }, [load])

  const polygons = useMemo(
    () =>
      fields
        .map((f) => ({ id: f.id, name: f.name, positions: geojsonToPositions(f.boundary_geojson) }))
        .filter((p) => p.positions.length > 2),
    [fields],
  )

  const visible = useMemo(() => {
    let out = applySeverityFilter(rows, filters).filter((r) => r.lat !== null && r.lon !== null)
    if (verifiedOnly) out = out.filter((r) => r.verification_status === 'technician_verified')
    return out
  }, [rows, filters, verifiedOnly])

  const withoutPosition = rows.length - rows.filter((r) => r.lat !== null && r.lon !== null).length
  const useCluster = visible.length > CLUSTER_ABOVE

  const markers = visible.map((det) => (
    <Marker
      key={det.id}
      position={[det.lat, det.lon]}
      icon={markerIcon(det.verification_status, det.severity)}
    >
      <Popup>
        <div style={{ minWidth: 190, fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{det.condition_name}</div>
          <div style={{ marginBottom: 4 }}>
            <StatusBadge status={det.verification_status} />
          </div>
          <div style={{ marginBottom: 4 }}>
            <ConfidenceLabel label={det.confidence_label} />
          </div>
          <div style={{ marginBottom: 8 }}>
            <SeverityTag value={det.severity} method={det.severity_method} />
          </div>
          <button className="as-btn" onClick={() => navigate(`/detections/${det.id}`)}>
            Open detection
          </button>
        </div>
      </Popup>
    </Marker>
  ))

  return (
    <div className="as-map-wrap">
      <aside className="as-map-side">
        <h2>Filters</h2>
        <Filters value={filters} onChange={setFilters} layout="stack" />

        <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '16px 0' }} />

        <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={verifiedOnly}
            onChange={(e) => setVerifiedOnly(e.target.checked)}
            style={{ marginTop: 3 }}
          />
          <span style={{ fontSize: 13 }}>Show technician-verified detections only</span>
        </label>

        {verifiedOnly ? (
          <div className="as-note">
            Showing verified detections only. Counts and any density reading on this map
            reflect expert-confirmed cases.
          </div>
        ) : (
          <div className="as-warn">
            This map includes unverified model output. Marker density is not a measure of
            disease presence until a technician has reviewed these cases.
          </div>
        )}

        <div style={{ margin: '16px 0', fontSize: 13 }}>
          <div>
            <strong>{visible.length}</strong> detections shown
            {loading && <span className="as-muted"> · refreshing</span>}
          </div>
          <div className="as-muted" style={{ fontSize: 12 }}>
            Within the current view. Pan or zoom to load more.
          </div>
          {withoutPosition > 0 && (
            <div className="as-muted" style={{ fontSize: 12, marginTop: 4 }}>
              {withoutPosition} detection{withoutPosition === 1 ? '' : 's'} not mapped —
              position missing.
            </div>
          )}
          {useCluster && (
            <div className="as-muted" style={{ fontSize: 12, marginTop: 4 }}>
              Clustering above {CLUSTER_ABOVE} markers.
            </div>
          )}
        </div>

        <h3>Legend</h3>
        <MapLegend />
        <p className="as-muted" style={{ fontSize: 12 }}>
          Marker fill shows severity; outline shows who has checked it.
        </p>

        {error && <div className="as-warn">{error}</div>}
      </aside>

      <div className="as-map">
        <BaseMapChoice value={baseMap} onChange={setBaseMap} />
        <MapContainer center={DEFAULT_CENTER} zoom={14} scrollWheelZoom>
          <BaseTiles layer={baseMap} />
          <BoundsWatcher onChange={setBounds} />
          <FitToFields polygons={polygons} />

          {polygons.map((polygon) => (
            <Polygon
              key={polygon.id}
              positions={polygon.positions}
              pathOptions={{ color: '#8BAF3F', weight: 2, fillOpacity: 0.08 }}
            >
              <Popup>{polygon.name}</Popup>
            </Polygon>
          ))}

          {useCluster ? (
            <MarkerClusterGroup chunkedLoading>{markers}</MarkerClusterGroup>
          ) : (
            markers
          )}
        </MapContainer>
      </div>
    </div>
  )
}
