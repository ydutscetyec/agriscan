import { useState } from 'react'
import { TileLayer } from 'react-leaflet'

/* The base map layers.
 *
 * OpenStreetMap's own tile servers started returning 403 "Access blocked — app is not
 * following the tile usage policy". Their policy is explicit that those servers are run
 * on donated hardware for OSM's own use, and that anything else needs its own source.
 * A research app on a shared tunnel hostname is exactly the traffic they cut off, so
 * pointing at them again with a different URL would just be waiting to break again.
 *
 * Esri's World Imagery is the default now, and is the better map for this work anyway:
 * satellite imagery shows paddies, bunds and water, where a street map of rural Surallah
 * is mostly blank. Both layers carry their required attribution.
 */
export const LAYERS = {
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
  },
  streets: {
    label: 'Streets',
    url: 'https://tile.openstreetmap.de/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  },
}

export function BaseTiles({ layer = 'satellite' }) {
  const l = LAYERS[layer] || LAYERS.satellite
  return <TileLayer key={layer} url={l.url} attribution={l.attribution} maxZoom={l.maxZoom} />
}

/** Small control for switching base maps. Sits outside the map, not over it. */
export function BaseMapChoice({ value, onChange }) {
  return (
    <div className="as-basemap">
      {Object.entries(LAYERS).map(([key, l]) => (
        <button
          key={key}
          type="button"
          className={`as-basemap-btn${value === key ? ' on' : ''}`}
          onClick={() => onChange(key)}
        >
          {l.label}
        </button>
      ))}
    </div>
  )
}

export function useBaseMap() {
  return useState('satellite')
}
