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
/* maxNativeZoom is the deepest level the provider actually has tiles for here, and it
 * is not the same as maxZoom. Past maxNativeZoom, Leaflet stretches the last real tile
 * instead of asking for one that does not exist — blurry, but the field is still
 * visible and the polygons stay put. Without it, Esri answers a request beyond its
 * coverage with a grey "Map data not yet available" placeholder at HTTP 200, which
 * looks exactly like a broken map.
 *
 * Esri's high-resolution imagery thins out over rural Mindanao well before z19. If 17
 * still looks stretched where you work, raise it and see; if a zoom level comes back
 * grey, lower it. maxZoom stays higher so the map can still be zoomed in to place a
 * boundary accurately.
 */
export const LAYERS = {
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
    maxNativeZoom: 17,
  },
  streets: {
    label: 'Streets',
    url: 'https://tile.openstreetmap.de/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
    maxNativeZoom: 18,
  },
}

/* A fit to a single small field would otherwise go straight to the map's maxZoom. A
 * one-hectare paddy is 100 m across, which is past every provider's coverage here. */
export const FIT_MAX_ZOOM = 17

export function BaseTiles({ layer = 'satellite' }) {
  const l = LAYERS[layer] || LAYERS.satellite
  return (
    <TileLayer
      key={layer}
      url={l.url}
      attribution={l.attribution}
      maxZoom={l.maxZoom}
      maxNativeZoom={l.maxNativeZoom}
    />
  )
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
