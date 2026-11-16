/* Visual components for the richer surface.
 *
 * Every one of these takes a real numerator and denominator. None of them accepts
 * a bare percentage, because a bare percentage is the easiest way for a fabricated
 * figure to reach a page that looks authoritative.
 */

const RING_R = 20
const RING_C = 2 * Math.PI * RING_R

/**
 * A ratio as an arc. `value` and `total` are counts, not a percentage.
 * With total = 0 the ring draws empty and reads "none yet" rather than 0%.
 */
export function Ring({ value, total, label, sub, tone = 'light' }) {
  const known = Number.isFinite(value) && Number.isFinite(total) && total > 0
  const frac = known ? Math.min(1, value / total) : 0
  const track = tone === 'dark' ? 'rgba(255,255,255,0.16)' : 'var(--gray-light)'
  const arc = tone === 'dark' ? 'var(--leaf-bright)' : 'var(--green)'

  return (
    <div className="as-ring">
      <svg width="48" height="48" viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="24" cy="24" r={RING_R} fill="none" stroke={track} strokeWidth="5" />
        {known && frac > 0 && (
          <circle
            cx="24" cy="24" r={RING_R} fill="none" stroke={arc} strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={`${RING_C * frac} ${RING_C}`}
            transform="rotate(-90 24 24)"
          />
        )}
      </svg>
      <div className="as-ring-text">
        <div className="as-ring-value">{Number.isFinite(value) ? value : '—'}</div>
        <div className="as-ring-label">{label}</div>
        {sub && <div className="as-ring-sub">{sub}</div>}
      </div>
    </div>
  )
}

/** A card with a named group, a title, and an optional figure in the corner. */
export function Section({ eyebrow, title, note, badge, badgeLabel, children }) {
  return (
    <section className="as-section">
      <div className="as-section-head">
        <div>
          {eyebrow && <div className="as-section-eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
          {note && <p className="as-section-note">{note}</p>}
        </div>
        {badge !== undefined && (
          <div className="as-badge">
            <div className="as-badge-value">{badge}</div>
            {badgeLabel && <div className="as-badge-label">{badgeLabel}</div>}
          </div>
        )}
      </div>
      {children}
    </section>
  )
}

/**
 * One class's progress toward the minimum-sample rule recorded in Chapter 3:
 * 150 verified samples, from at least 3 fields, across at least 2 visit dates.
 * A class failing any of the three is not trainable, however full the bar looks.
 */
export function ReadinessRow({ name, verified, fields, dates, minSamples }) {
  const frac = Math.min(1, verified / minSamples)
  const enough = verified >= minSamples && fields >= 3 && dates >= 2
  const colour = enough ? 'var(--green)'
    : verified >= minSamples ? 'var(--sev-moderate)'
    : 'var(--sev-unknown)'

  const blocker = enough ? null
    : verified < minSamples ? `${minSamples - verified} more`
    : fields < 3 ? `${3 - fields} more field${3 - fields === 1 ? '' : 's'}`
    : `${2 - dates} more date${2 - dates === 1 ? '' : 's'}`

  return (
    <div className="as-ready-row">
      <div>
        <div className="as-ready-name">{name}</div>
        <div className="as-ready-sub">
          {verified} verified · {fields} field{fields === 1 ? '' : 's'} · {dates} date{dates === 1 ? '' : 's'}
        </div>
      </div>
      <div className="as-ready-track" role="img"
           aria-label={`${verified} of ${minSamples} verified samples`}>
        <span style={{ width: `${frac * 100}%`, background: colour }} />
      </div>
      <div className="as-ready-state" style={{ color: colour }}>
        {enough ? 'Trainable' : blocker}
      </div>
    </div>
  )
}
