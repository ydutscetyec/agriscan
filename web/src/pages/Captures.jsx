import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, Images, Trash2, X } from 'lucide-react'
import { api, fetchImageObjectUrl, sessionZipUrl } from '../api/client'
import { PageHeader } from '../components/Layout'
import { useAuth } from '../state/auth'

/* Every photo that has reached the server, analysed or not.
 *
 * The Overview counts images captured, and before this page there was nowhere to go and
 * look at them: Detections only lists model output, so a photo that is queued, was
 * rejected by the quality gate, or was judged not to be palay existed as a number on
 * the Overview and nothing else. That is exactly the photo an operator needs to see. */

const JOB_TEXT = {
  QUEUED: ['Waiting', 'In the queue. Nothing is analysing it yet — check that the worker is running.'],
  RETRYING: ['Retrying', 'A previous attempt failed and it has been put back in the queue.'],
  RUNNING: ['Analysing', 'A worker has it now.'],
  COMPLETED: ['Analysed', 'The model has finished with this photo.'],
  FAILED: ['Failed', 'The worker could not finish. The worker log says why.'],
}

function Status({ capture }) {
  const [label, hint] = JOB_TEXT[capture.job_status] || ['Not queued', 'No analysis job exists for this photo.']
  const tone = { FAILED: 'bad', COMPLETED: 'good' }[capture.job_status] || 'wait'
  return <span className={`as-cap-status ${tone}`} title={hint}>{label}</span>
}

/* Full-size view. The thumbnail on a card is 84 px; checking whether a frame is sharp,
   framed and actually of rice needs the real picture. */
function Lightbox({ capture, onClose }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let url = null
    let alive = true
    fetchImageObjectUrl(capture.image_id)
      .then((u) => {
        if (!alive) return URL.revokeObjectURL(u)
        url = u
        return setSrc(u)
      })
      .catch(() => alive && setFailed(true))
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      alive = false
      if (url) URL.revokeObjectURL(url)
      window.removeEventListener('keydown', onKey)
    }
  }, [capture.image_id, onClose])

  return (
    <div className="as-lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="as-lightbox-inner" onClick={(e) => e.stopPropagation()}>
        <div className="as-lightbox-bar">
          <span>
            #{capture.image_id} · {capture.field_name} · {capture.source}
            {capture.captured_at && ` · ${new Date(capture.captured_at).toLocaleString()}`}
          </span>
          <button type="button" className="as-tour-close" onClick={onClose}
                  aria-label="Close the picture">
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>
        {failed
          ? <div className="as-lightbox-empty">The file is not on this server.</div>
          : src
            ? <img className="as-lightbox-img" src={src} alt={`Capture ${capture.image_id}`} />
            : <div className="as-lightbox-empty">Loading the full picture…</div>}
      </div>
    </div>
  )
}

function Thumb({ capture }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)
  const [near, setNear] = useState(false)
  const box = useRef(null)

  // Only fetch what is on or near the screen. A season of flights is thousands of rows,
  // and firing every request at once makes the first screen slower, not faster.
  useEffect(() => {
    const el = box.current
    if (!el || near) return undefined
    if (typeof IntersectionObserver === 'undefined') {
      setNear(true)
      return undefined
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setNear(true)
    }, { rootMargin: '300px' })
    io.observe(el)
    return () => io.disconnect()
  }, [near])

  useEffect(() => {
    if (!near) return undefined
    let revoke = null
    let alive = true
    // The file endpoint needs the auth header, so it cannot go straight into <img src>.
    fetchImageObjectUrl(capture.image_id, { thumb: true })
      .then((url) => {
        if (!alive) return URL.revokeObjectURL(url)
        revoke = url
        return setSrc(url)
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
      if (revoke) URL.revokeObjectURL(revoke)
    }
  }, [capture.image_id, near])

  if (failed) {
    return (
      <div ref={box} className="as-cap-thumb missing" title="The file is not on this server">
        no file
      </div>
    )
  }
  if (!src) return <div ref={box} className="as-cap-thumb loading" />
  return <img ref={box} className="as-cap-thumb" src={src} alt="" loading="lazy" />
}

export default function Captures() {
  const { user } = useAuth()
  const [params] = useSearchParams()
  const sessionId = params.get('session')
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [notice, setNotice] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [bulk, setBulk] = useState(null)

  const [total, setTotal] = useState(0)

  const load = () => api.captures(100, sessionId)
    .then((r) => {
      setRows(r.captures)
      setTotal(r.total ?? r.captures.length)
      // Drop ids that are no longer listed, so the count can never claim more than
      // is on screen after a delete, a filter change or someone else's edit.
      setSelected((prev) => {
        const live = new Set(r.captures.map((c) => c.image_id))
        return new Set([...prev].filter((id) => live.has(id)))
      })
    })
    .catch((e) => setError(e.message))

  useEffect(() => { load() }, [sessionId])

  async function remove(capture) {
    const ok = window.confirm(
      `Delete photo #${capture.image_id} from ${capture.field_name}?\n\n`
      + 'The file and anything the model found on it are removed for good. '
      + 'A record that you deleted it is kept.',
    )
    if (!ok) return
    setBusy(capture.image_id)
    setError(null)
    setNotice(null)
    try {
      const result = await api.deleteCapture(capture.image_id)
      setNotice(
        `Deleted photo #${capture.image_id}.`
        + (result.file_removed ? '' : ' The database row is gone; the file was already missing from disk.'),
      )
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  function toggle(imageId) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(imageId)) next.delete(imageId)
      else next.add(imageId)
      return next
    })
  }

  /* Deleted one at a time: there is no bulk endpoint, and inventing a client-side
     "all or nothing" over separate requests would be a lie -- the early ones are
     already gone. Sequential rather than parallel so a slip of the mouse on 200
     photos does not arrive as 200 simultaneous deletes, and so the count below is
     a truthful running total. Failures are collected and named rather than
     stopping the run, because a photo that is already gone should not block the
     rest. */
  async function removeSelected() {
    const ids = [...selected]
    if (!ids.length || bulk) return
    const ok = window.confirm(
      `Delete ${ids.length} photo${ids.length === 1 ? '' : 's'}?\n\n`
      + 'The files and anything the model found on them are removed for good. '
      + 'A record that you deleted them is kept.',
    )
    if (!ok) return
    setError(null)
    setNotice(null)
    const failed = []
    let done = 0
    for (const id of ids) {
      setBulk({ done, total: ids.length })
      try {
        await api.deleteCapture(id)
      } catch (e) {
        failed.push(`#${id} (${e.message})`)
      }
      done += 1
    }
    setBulk(null)
    const deleted = ids.length - failed.length
    setNotice(`Deleted ${deleted} photo${deleted === 1 ? '' : 's'}.`)
    if (failed.length) setError(`Could not delete ${failed.length}: ${failed.join(', ')}`)
    await load()
  }

  const waiting = (rows || []).filter((r) => ['QUEUED', 'RETRYING'].includes(r.job_status)).length

  /* Grouped by the session that produced them. A flight is the unit people think in —
     "the photos from Tuesday's pass over Field A" — and a flat list of 300 captures
     mixed with phone photos is not that. */
  const groups = []
  for (const capture of rows || []) {
    const key = capture.capture_session_id ?? 'none'
    let group = groups.find((g) => g.key === key)
    if (!group) {
      group = { key, sessionId: capture.capture_session_id, items: [] }
      groups.push(group)
    }
    group.items.push(capture)
  }

  async function downloadSession(sessionId) {
    setError(null)
    try {
      // The endpoint needs the auth header, so the file is fetched and then handed to
      // the browser as a blob rather than opened as a plain link.
      const response = await fetch(sessionZipUrl(sessionId), {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('agriscan_token')}` },
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.error || `Download failed (${response.status})`)
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `agriscan-session-${sessionId}.zip`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Capture"
        icon={Images}
        title="Captured images"
        description={sessionId
          ? `Photos from capture session ${sessionId} only.`
          : 'Every photo on this server, whether or not the model has looked at it yet. Detections only lists model output, so a queued or rejected photo appears here and nowhere else.'}
        meta={rows ? `${rows.length} shown${total > rows.length ? ` of ${total}` : ''}${waiting ? ` · ${waiting} waiting for analysis` : ''}` : null}
      />

      {rows && total > rows.length && (
        <div className="as-note" role="status">
          Showing the {rows.length} most recent of {total} photos. Older ones are on the
          server and counted, they are just not on this page yet.
        </div>
      )}
      {sessionId && (
        <div className="as-note" role="status">
          Filtered to session {sessionId}. <Link to="/captures">Show all photos</Link>
        </div>
      )}
      {error && <div className="as-warn" role="alert">{error}</div>}
      {notice && <div className="as-note" role="status">{notice}</div>}
      {!rows && !error && <div className="as-empty">Loading…</div>}
      {rows && rows.length === 0 && (
        <div className="as-empty">
          {sessionId
            ? 'This session produced no photos. If its status is Expired and the phone never reported, the phone never picked the session up — check that /camera was open and signed in on the same address as this dashboard.'
            : 'No photos yet. Start a capture session from Drone camera, or add photos from Upload images.'}
        </div>
      )}

      {user?.role === 'admin' && rows && rows.length > 0 && (
        <div className="as-cap-bar">
          <span className="as-cap-bar-count">
            {selected.size
              ? `${selected.size} selected`
              : 'Tick photos to delete several at once'}
          </span>
          <button type="button" className="as-btn secondary as-btn-sm" disabled={!!bulk}
                  onClick={() => setSelected(new Set(rows.map((r) => r.image_id)))}>
            Select all {rows.length} shown
          </button>
          <button type="button" className="as-btn secondary as-btn-sm"
                  disabled={!selected.size || !!bulk}
                  onClick={() => setSelected(new Set())}>
            Clear
          </button>
          <button type="button" className="as-btn as-btn-sm as-cap-bar-del"
                  disabled={!selected.size || !!bulk}
                  onClick={removeSelected}>
            <Trash2 size={15} strokeWidth={1.8} />
            {bulk
              ? `Deleting ${bulk.done + 1} of ${bulk.total}\u2026`
              : `Delete selected${selected.size ? ` (${selected.size})` : ''}`}
          </button>
        </div>
      )}

      {viewing && <Lightbox capture={viewing} onClose={() => setViewing(null)} />}

      {rows && rows.length > 0 && (
        groups.map((group) => (
          <section key={group.key} className="as-cap-group">
            <div className="as-cap-group-head">
              <h2>
                {group.sessionId
                  ? <Link to={`/captures?session=${group.sessionId}`}>Session {group.sessionId}</Link>
                  : 'Not from a capture session'}
                <span className="as-muted"> · {group.items.length} photo{group.items.length === 1 ? '' : 's'}</span>
              </h2>
              {group.sessionId && (
                <button type="button" className="as-btn secondary as-btn-sm"
                        onClick={() => downloadSession(group.sessionId)}>
                  <Download size={14} strokeWidth={1.8} /> Download all
                </button>
              )}
            </div>
            <div className="as-cap-grid">
          {group.items.map((capture) => (
            <article className="as-cap" key={capture.image_id}>
              {user?.role === 'admin' && (
                <label className="as-cap-pick" title={`Select photo ${capture.image_id}`}>
                  <input type="checkbox" checked={selected.has(capture.image_id)}
                         disabled={!!bulk}
                         onChange={() => toggle(capture.image_id)}
                         aria-label={`Select photo ${capture.image_id} for deletion`} />
                </label>
              )}
              <button type="button" className="as-cap-open" onClick={() => setViewing(capture)}
                      title="View the full picture"
                      aria-label={`View photo ${capture.image_id} full size`}>
                <Thumb capture={capture} />
              </button>
              <div className="as-cap-info">
                <div className="as-cap-top">
                  <span className="as-cap-id">#{capture.image_id}</span>
                  <Status capture={capture} />
                </div>
                <div className="as-cap-meta">
                  {capture.field_name} · {capture.source}
                  {capture.captured_at && <> · {new Date(capture.captured_at).toLocaleString()}</>}
                </div>
                {capture.quality_flag && capture.quality_flag !== 'ok' && (
                  <div className="as-cap-flag">Quality: {capture.quality_flag}</div>
                )}
                {capture.detection ? (
                  <Link to={`/detections/${capture.detection.detection_id}`} className="as-cap-link">
                    {capture.detection.condition_code}
                    {capture.detection_count > 1 && ` +${capture.detection_count - 1} more`}
                  </Link>
                ) : (
                  <div className="as-cap-none">No detection on this photo.</div>
                )}
              </div>
              {user?.role === 'admin' && (
                <button
                  type="button"
                  className="as-cap-delete"
                  onClick={() => remove(capture)}
                  disabled={busy === capture.image_id || !!bulk}
                  aria-label={`Delete photo ${capture.image_id}`}
                  title="Delete this photo"
                >
                  <Trash2 size={16} strokeWidth={1.75} />
                </button>
              )}
            </article>
          ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
