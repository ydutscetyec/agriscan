/**
 * The one place a detection's verification state is turned into pixels.
 *
 * Every page that shows a detection imports from here. If you find yourself writing
 * `detection.status` into JSX anywhere else, that is the bug: a detection rendered
 * without its status is a claim the system cannot support.
 *
 * Shape carries the meaning, not colour alone. An unverified detection is hollow or
 * dashed; a verified one is solid. That distinction survives greyscale printing, a
 * projector, and colour-blind readers.
 */

import L from 'leaflet'

export const STATUS = {
  ai_detected: {
    label: 'AI detected',
    short: 'AI DETECTED',
    fill: 'none',
    stroke: '#6B7280',
    dash: false,
    struck: false,
    note: 'Model output only. No person has checked this.',
  },
  low_confidence: {
    label: 'Low confidence',
    short: 'LOW CONFIDENCE',
    fill: 'none',
    stroke: '#9AA0A6',
    dash: true,
    struck: false,
    note: 'Below the confidence threshold. Technician review required.',
  },
  farmer_confirmed: {
    label: 'Farmer confirmed',
    short: 'FARMER CONFIRMED',
    fill: 'half',
    stroke: '#648B2F',
    dash: false,
    struck: false,
    note: 'The farmer agrees. Not an expert diagnosis.',
  },
  technician_verified: {
    label: 'Technician verified',
    short: 'TECHNICIAN VERIFIED',
    fill: 'solid',
    stroke: '#648B2F',
    dash: false,
    struck: false,
    note: 'Confirmed by an agricultural technician.',
  },
  rejected: {
    label: 'Rejected',
    short: 'REJECTED',
    fill: 'none',
    stroke: '#B23B2E',
    dash: false,
    struck: true,
    note: 'A technician disagreed with this detection.',
  },
}

export function statusOf(status) {
  return STATUS[status] || STATUS.low_confidence
}

/** Severity band. Thresholds are presentation only; the number is what matters. */
export function severityBand(value) {
  if (value === null || value === undefined) {
    return { word: 'Not measured', color: 'var(--sev-unknown)' }
  }
  if (value <= 0.5) return { word: 'None', color: 'var(--sev-none)' }
  if (value < 10) return { word: 'Mild', color: 'var(--sev-mild)' }
  if (value < 30) return { word: 'Moderate', color: 'var(--sev-moderate)' }
  return { word: 'Severe', color: 'var(--sev-severe)' }
}

/* ------------------------------------------------------------------ components */

export function StatusBadge({ status, title }) {
  const s = statusOf(status)
  const swatch = {
    display: 'inline-block',
    width: 11,
    height: 11,
    borderRadius: '50%',
    border: `2px ${s.dash ? 'dashed' : 'solid'} ${s.stroke}`,
    background:
      s.fill === 'solid'
        ? s.stroke
        : s.fill === 'half'
        ? `linear-gradient(90deg, ${s.stroke} 50%, transparent 50%)`
        : 'transparent',
    marginRight: 6,
    flex: '0 0 auto',
  }
  return (
    <span
      className="as-statusbadge"
      data-status={status}
      title={title || s.note}
      style={{ display: 'inline-flex', alignItems: 'center', whiteSpace: 'nowrap' }}
    >
      <span style={swatch} aria-hidden="true" />
      <span
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: s.stroke,
          textDecoration: s.struck ? 'line-through' : 'none',
        }}
      >
        {s.label}
      </span>
    </span>
  )
}

/** Colour + word + number, always all three. */
export function SeverityTag({ value, method }) {
  const band = severityBand(value)
  const shown = value === null || value === undefined ? '—' : `${value.toFixed(1)}%`
  return (
    <span
      className="as-sevchip"
      data-sev={band.word}
      title={
        method
          ? `Method: ${method}. EXPERIMENTAL, not validated against technician scoring.`
          : undefined
      }
    >
      {band.word}
      <span style={{ opacity: 0.75, fontWeight: 500 }}>{shown}</span>
    </span>
  )
}


/**
 * Confidence is never shown as a bare number and never called certainty.
 * The words "model confidence" are part of the value, not a caption.
 */
export function ConfidenceLabel({ value, label }) {
  if (label) return <span>{label}</span>
  if (value === null || value === undefined) return <span className="as-muted">Not available</span>
  return <span>{(value * 100).toFixed(1)}% model confidence</span>
}

/* ---------------------------------------------------------------- map markers */

/**
 * Leaflet divIcon matching the badge exactly: same shape language on the map as in
 * every table, so a reader learns one vocabulary.
 */
export function markerIcon(status, severityValue) {
  const s = statusOf(status)
  const band = severityBand(severityValue)
  const size = 16
  const fill =
    s.fill === 'solid'
      ? band.color
      : s.fill === 'half'
      ? `linear-gradient(90deg, ${band.color} 50%, rgba(255,255,255,0.85) 50%)`
      : 'rgba(255,255,255,0.85)'

  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<span style="
      display:block;width:${size}px;height:${size}px;border-radius:50%;
      background:${fill};
      border:2px ${s.dash ? 'dashed' : 'solid'} ${s.stroke};
      box-shadow:0 0 0 1px rgba(255,255,255,0.9);
      ${s.struck ? 'opacity:.75;' : ''}"></span>`,
  })
}

export function MapLegend() {
  return (
    <div className="as-legend">
      {Object.entries(STATUS).map(([key, s]) => (
        <div className="as-legend-row" key={key}>
          <span
            aria-hidden="true"
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              border: `2px ${s.dash ? 'dashed' : 'solid'} ${s.stroke}`,
              background:
                s.fill === 'solid'
                  ? s.stroke
                  : s.fill === 'half'
                  ? `linear-gradient(90deg, ${s.stroke} 50%, transparent 50%)`
                  : 'transparent',
              flex: '0 0 auto',
            }}
          />
          <span style={{ textDecoration: s.struck ? 'line-through' : 'none' }}>{s.label}</span>
        </div>
      ))}
    </div>
  )
}
