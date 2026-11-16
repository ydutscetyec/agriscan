import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { addCapture } from '../db'
import { Bi } from '../labels'
import { Camera, Image as ImageIcon, RotateCcw } from 'lucide-react'

/* Submitting never touches the network. The capture goes to IndexedDB and the sync
   loop takes it from there, so the button behaves identically with or without signal. */
export default function Capture({ onQueued, online }) {
  const [fields, setFields] = useState([])
  const [fieldId, setFieldId] = useState('')
  const [zoneRef, setZoneRef] = useState('')
  const [note, setNote] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [saved, setSaved] = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    api
      .fields()
      .then((rows) => {
        setFields(rows)
        if (rows.length === 1) setFieldId(String(rows[0].id))
      })
      .catch(() => setError('Field list unavailable offline. Reconnect once to load it.'))
  }, [])

  useEffect(() => {
    if (!file) return undefined
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  async function submit(event) {
    event.preventDefault()
    // A double-tap on a phone in the sun is the normal case, not an edge case.
    // Without this guard it saved two captures of the same photo.
    if (saving) return
    setError(null)
    if (!file) {
      setError('Take a photo first.')
      return
    }
    if (!fieldId) {
      setError('Choose which field this is.')
      return
    }
    setSaving(true)
    try {
      const record = await addCapture({
        blob: file,
        fieldId: Number(fieldId),
        source: 'phone',
        zoneRef: zoneRef || null,
        note: note || null,
      })
      setSaved(record.clientUuid)
      setFile(null)
      setPreview(null)
      setZoneRef('')
      setNote('')
      if (inputRef.current) inputRef.current.value = ''
      onQueued?.()
    } catch (err) {
      setError(`Could not save the photo on this phone: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <h1 style={{ fontSize: 20 }}>
        <Bi k="capture" />
      </h1>

      {saved && (
        <div className="as-note" style={{ marginBottom: 16 }}>
          <strong>Saved on this phone.</strong>{' '}
          {online
            ? 'Sending now. Your result will appear under My results.'
            : 'Queued — will analyse when connected.'}
        </div>
      )}

      <div className="fc-card">
      <p className="fc-step" data-n="1">Photo</p>
      <label className="fc-shutter" htmlFor="shot">
        {file
          ? <><RotateCcw size={22} strokeWidth={2} /> Take another photo</>
          : <><Camera size={24} strokeWidth={2} /> Take a photo of the plant</>}
      </label>
      <input
        id="shot"
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="fc-fileinput"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />

      {/* capture="environment" opens the camera and nothing else. A farmer who
          already photographed the crop had no way to send it. */}
      <label className="fc-gallery" htmlFor="shot-gallery">
        <ImageIcon size={18} strokeWidth={1.9} /> <Bi k="gallery" />
      </label>
      <input
        id="shot-gallery"
        type="file"
        accept="image/*"
        className="fc-fileinput"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />

      <details className="fc-tips">
        <summary><Bi k="photoTips" /></summary>
        <ul>
          <li>Fill the frame with the affected leaf or panicle.</li>
          <li>Hold still and tap the screen to focus before shooting.</li>
          <li>Stand so your shadow falls away from the plant, not across it.</li>
          <li>One plant part per photo. Several problems in one frame cannot be scored.</li>
        </ul>
        <p>Blurred or very dark photos are rejected before the model sees them.</p>
      </details>

      {preview ? (
        <img src={preview} alt="The photo you just took" className="fc-preview" />
      ) : (
        <div className="fc-slot">No photo yet</div>
      )}

      </div>

      <div className="fc-card">
      <p className="fc-step" data-n="2">Where</p>
      <div className="as-field">
        <label className="as-label" htmlFor="c-field">
          <Bi k="field" />
        </label>
        <select
          id="c-field"
          className="as-select"
          value={fieldId}
          onChange={(e) => setFieldId(e.target.value)}
        >
          <option value="">Choose a field…</option>
          {fields.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="c-zone">
          <Bi k="zone" /> <span className="as-optional">optional</span>
        </label>
        <input
          id="c-zone"
          className="as-input"
          value={zoneRef}
          onChange={(e) => setZoneRef(e.target.value)}
          placeholder="e.g. Zone B"
        />
        <span className="as-help">Only if the drone flagged a spot.</span>
      </div>

      <div className="as-field">
        <label className="as-label" htmlFor="c-note">
          <Bi k="note" /> <span className="as-optional">optional</span>
        </label>
        <textarea
          id="c-note"
          className="as-textarea"
          rows={3}
          value={note}
          maxLength={200}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="fc-counter">
          <span className="as-help">How the crop looks, in your own words.</span>
          <span className={note.length > 180 ? 'near' : undefined}>{note.length}/200</span>
        </div>
      </div>

      {error && (
        <div className="as-warn" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      </div>

      <div className="fc-card">
      <p className="fc-step" data-n="3">Send</p>
      <button className="as-btn block lg" data-busy={saving} disabled={saving || !file}>
        {saving ? 'Saving…' : <Bi k="send" />}
      </button>
      {!file && (
        <p className="fc-needphoto">Take a photo first.</p>
      )}

      <p className="fc-hint">
        The photo is analysed on the AGRISCAN server, not on your phone. If you have no
        signal it waits here until you do.
      </p>
      </div>
    </form>
  )
}
