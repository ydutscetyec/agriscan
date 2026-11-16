/* Small shared layout pieces. Each does one job. */

/**
 * Shared by every content page. `eyebrow` names the group the page sits in, so a
 * page read on its own still says where it belongs. `icon` and `meta` are optional;
 * meta takes a short fact the page already knows, never a decorative figure.
 */
export function PageHeader({ title, description, actions, eyebrow, icon: Icon, meta }) {
  return (
    <header className="as-pagehead">
      <div className="as-pagehead-main">
        {Icon && (
          <span className="as-pagehead-icon" aria-hidden="true">
            <Icon size={20} strokeWidth={1.7} />
          </span>
        )}
        <div>
          {eyebrow && <div className="as-pagehead-eyebrow">{eyebrow}</div>}
          <h1>{title}</h1>
          {description && <p>{description}</p>}
          {meta && <div className="as-pagehead-meta">{meta}</div>}
        </div>
      </div>
      {actions && <div className="as-pagehead-actions">{actions}</div>}
    </header>
  )
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="as-emptystate">
      {Icon && (
        <div className="as-emptystate-icon" aria-hidden="true">
          <Icon size={20} strokeWidth={1.75} />
        </div>
      )}
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

/* The brand mark: paddies seen from the air, divided by dikes, with a scan bracket.
   Drawn, not an emoji, so it reproduces cleanly in the paper and the favicon. */
export function BrandMark({ size = 30 }) {
  return (
    <svg className="as-brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="6" fill="#E8EDE0" />
      <rect x="7" y="7" width="8" height="8" rx="1" fill="#8BAF3F" />
      <rect x="17" y="7" width="8" height="8" rx="1" fill="#648B2F" />
      <rect x="7" y="17" width="8" height="8" rx="1" fill="#648B2F" />
      <rect x="17" y="17" width="8" height="8" rx="1" fill="#2C3A31" />
      <path d="M4 9V4h5M23 4h5v5M28 23v5h-5M9 28H4v-5" stroke="#2C3A31" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}

/**
 * A field's actual drawn boundary as a thumbnail. This is data, not decoration:
 * the shape a farmer sees is the shape stored in the database.
 * GeoJSON is [lon, lat]; latitude is flipped so north is up.
 */
export function FieldShape({ geojson, size = 64 }) {
  const geometry = geojson?.type === 'Feature' ? geojson.geometry : geojson
  const ring = geometry?.type === 'Polygon' ? geometry.coordinates?.[0] || [] : []
  if (ring.length < 3) {
    return (
      <svg className="as-fieldshape" width={size} height={size} viewBox="0 0 64 64" aria-label="No boundary drawn">
        <rect x="14" y="14" width="36" height="36" rx="2" fill="none" stroke="#9AA0A6" strokeWidth="1.5" strokeDasharray="4 3" />
      </svg>
    )
  }
  const lons = ring.map((p) => p[0])
  const lats = ring.map((p) => p[1])
  const minX = Math.min(...lons), maxX = Math.max(...lons)
  const minY = Math.min(...lats), maxY = Math.max(...lats)
  // Correct longitude for latitude so the shape is not stretched east-west.
  const k = Math.cos(((minY + maxY) / 2) * Math.PI / 180)
  const w = (maxX - minX) * k || 1e-9
  const h = (maxY - minY) || 1e-9
  const scale = 48 / Math.max(w, h)
  const offX = (64 - w * scale) / 2
  const offY = (64 - h * scale) / 2
  const points = ring
    .map(([lon, lat]) => `${(offX + (lon - minX) * k * scale).toFixed(1)},${(offY + (maxY - lat) * scale).toFixed(1)}`)
    .join(' ')
  return (
    <svg className="as-fieldshape" width={size} height={size} viewBox="0 0 64 64" aria-label="Field boundary shape">
      <polygon points={points} fill="#8BAF3F" fillOpacity="0.35" stroke="#648B2F" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
