import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload as UploadIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, uploadImageWithProgress } from '../api/client'
import { PageHeader } from '../components/Layout'

/* Desktop upload for technicians working from a laptop: drone frames copied off the
   phone, or close-range captures brought back from the field. Farmers use /field. */

const ACCEPT = ['image/jpeg', 'image/png']
const ACCEPT_EXT = ['.jpg', '.jpeg', '.png']
const MAX_BYTES = 15 * 1024 * 1024

function validate(file) {
  if (!file) return 'No file selected.'
  if (file.size === 0) return 'This file is empty.'
  if (file.size > MAX_BYTES) return 'This file is larger than 15 MB.'
  const ext = `.${(file.name.split('.').pop() || '').toLowerCase()}`
  if (!ACCEPT.includes(file.type) || !ACCEPT_EXT.includes(ext)) {
    return 'This file is not a supported image format. Use JPG or PNG.'
  }
  return null
}

function StatusLine({ item }) {
  if (item.state === 'invalid') return <span style={{ color: 'var(--sev-severe)' }}>{item.error}</span>
  if (item.state === 'uploading') return <span>Uploading… {item.progress}%</span>
  if (item.state === 'failed') return <span style={{ color: 'var(--sev-severe)' }}>{item.error}</span>
  if (item.state === 'duplicate') {
    return (
      <span>
        Image already exists —{' '}
        <Link to={`/detections?image=${item.imageId}`}>already on record</Link>
      </span>
    )
  }
  if (item.state === 'queued') {
    return (
      <span style={{ color: 'var(--sev-none)' }}>
        Inference queued.
        {item.gpsNote ? <span className="as-muted"> {item.gpsNote}</span> : null}
      </span>
    )
  }
  return <span className="as-muted">Ready</span>
}

export default function Upload() {
  const [fields, setFields] = useState([])
  const [fieldId, setFieldId] = useState('')
  const [source, setSource] = useState('phone')
  const [items, setItems] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    api.fields().then(setFields).catch(() => setFields([]))
  }, [])

  // Free preview object URLs when the list changes or the page unmounts.
  useEffect(() => () => items.forEach((i) => i.preview && URL.revokeObjectURL(i.preview)), [])

  const addFiles = useCallback((fileList) => {
    const next = Array.from(fileList).map((file) => {
      const error = validate(file)
      return {
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`,
        file,
        preview: error ? null : URL.createObjectURL(file),
        state: error ? 'invalid' : 'ready',
        error,
        progress: 0,
      }
    })
    setItems((current) => [...current, ...next])
  }, [])

  function remove(id) {
    setItems((current) => {
      const target = current.find((i) => i.id === id)
      if (target?.preview) URL.revokeObjectURL(target.preview)
      return current.filter((i) => i.id !== id)
    })
  }

  function patch(id, change) {
    setItems((current) => current.map((i) => (i.id === id ? { ...i, ...change } : i)))
  }

  async function uploadAll() {
    if (!fieldId || busy) return
    setBusy(true)
    const pending = items.filter((i) => i.state === 'ready' || i.state === 'failed')
    // Sequential, not parallel: a weak rural uplink handles one file far better than six.
    for (const item of pending) {
      patch(item.id, { state: 'uploading', progress: 0, error: null })
      try {
        const result = await uploadImageWithProgress(
          { file: item.file, fieldId, source },
          (progress) => patch(item.id, { progress }),
        )
        patch(item.id, {
          state: result.duplicate ? 'duplicate' : 'queued',
          imageId: result.image_id,
          gpsNote: result.gps_note,
          progress: 100,
        })
      } catch (err) {
        patch(item.id, {
          state: 'failed',
          error: err.message || 'Upload failed. Please check your connection and try again.',
        })
      }
    }
    setBusy(false)
  }

  const readyCount = items.filter((i) => i.state === 'ready' || i.state === 'failed').length
  const doneCount = items.filter((i) => i.state === 'queued' || i.state === 'duplicate').length

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Capture"
        icon={UploadIcon} title="Upload images" description="For images already on this computer. Analysis runs on the server after upload; results appear under Detections once the worker has processed them." />

      <div className="as-card plain" style={{ marginBottom: 16 }}>
        <div className="as-grid cols-2">
          <div className="as-field">
            <label className="as-label" htmlFor="u-field">Field</label>
            <select id="u-field" className="as-select" value={fieldId}
                    onChange={(e) => setFieldId(e.target.value)} disabled={busy}>
              <option value="">Choose a field…</option>
              {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
          <div className="as-field">
            <label className="as-label" htmlFor="u-source">Image source</label>
            <select id="u-source" className="as-select" value={source}
                    onChange={(e) => setSource(e.target.value)} disabled={busy}>
              <option value="phone">Phone — close range</option>
              <option value="drone">Drone — aerial, zone-level only</option>
            </select>
          </div>
        </div>
        {source === 'drone' && (
          <p className="as-muted" style={{ fontSize: 12, margin: 0 }}>
            Aerial frames can only receive zone-level labels. A drone image will never be
            given a specific disease diagnosis.
          </p>
        )}
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Drop images here or press Enter to choose files"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click() }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (!busy) addFiles(e.dataTransfer.files)
        }}
        style={{
          border: `2px dashed ${dragging ? 'var(--green)' : 'var(--border)'}`,
          background: dragging ? 'var(--green-light)' : '#fff',
          borderRadius: 'var(--radius-lg)',
          padding: '36px 16px',
          textAlign: 'center',
          cursor: busy ? 'not-allowed' : 'pointer',
          marginBottom: 16,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 4 }}>
          Drop images here, or click to choose
        </div>
        <div className="as-muted" style={{ fontSize: 12.5 }}>
          JPG or PNG, up to 15 MB each. Several at once is fine.
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_EXT.join(',')}
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { addFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      {items.length > 0 && (
        <div className="as-card plain" style={{ marginBottom: 16 }}>
          {items.map((item) => (
            <div key={item.id} style={{
              display: 'flex', gap: 12, alignItems: 'center',
              padding: '8px 0', borderBottom: '1px solid var(--border)',
            }}>
              {item.preview ? (
                <img src={item.preview} alt={`Preview of ${item.file.name}`}
                     style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 4 }} />
              ) : (
                <div style={{ width: 56, height: 56, background: 'var(--gray-light)', borderRadius: 4 }} />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.file.name}
                </div>
                <div style={{ fontSize: 12.5 }}><StatusLine item={item} /></div>
                {item.state === 'uploading' && (
                  <div style={{ height: 4, background: 'var(--gray-light)', borderRadius: 2, marginTop: 4 }}>
                    <div style={{ height: 4, width: `${item.progress}%`, background: 'var(--green)', borderRadius: 2 }} />
                  </div>
                )}
              </div>
              {(item.state === 'ready' || item.state === 'invalid' || item.state === 'failed') && (
                <button type="button" className="as-btn secondary" disabled={busy}
                        onClick={() => remove(item.id)}>
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <button className="as-btn" onClick={uploadAll} data-busy={busy}
                disabled={busy || !fieldId || readyCount === 0}>
          {busy ? 'Uploading…' : `Upload ${readyCount || ''} image${readyCount === 1 ? '' : 's'}`}
        </button>
        {!fieldId && items.length > 0 && (
          <span className="as-muted" style={{ fontSize: 12.5 }}>Choose a field first.</span>
        )}
        {doneCount > 0 && !busy && (
          <Link to="/detections">See detections</Link>
        )}
      </div>
    </div>
  )
}
