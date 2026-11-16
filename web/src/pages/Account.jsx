import { useState } from 'react'
import { KeyRound } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../state/auth'
import { PageHeader } from '../components/Layout'

const MIN_PASSWORD = 10
const ROLE_TEXT = {
  farmer: 'Farmer: sends photos and sees results for your own fields.',
  technician: 'Technician: verifies detections and approves advice.',
  researcher: 'Researcher: data and analysis.',
  admin: 'Administrator: accounts and settings.',
}

/** Change-password form. Shared by the dashboard page and the farmer's field client. */
export function ChangePasswordForm({ compact = false }) {
  const { replaceSession } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD
  const mismatch = repeat.length > 0 && repeat !== next

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setError(null)
    setDone(false)
    if (next.length < MIN_PASSWORD) return setError(`The new password needs at least ${MIN_PASSWORD} characters.`)
    if (next !== repeat) return setError('The two new passwords do not match.')
    setBusy(true)
    try {
      const result = await api.changePassword(current, next)
      replaceSession(result.token, result.user)
      setCurrent('')
      setNext('')
      setRepeat('')
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className={`as-card plain as-account-form${compact ? ' compact' : ''}`} onSubmit={submit}>
      <h2>Change password</h2>
      <p className="as-muted as-account-hint">
        Every other phone or computer signed in to this account will be signed out.
        This one stays signed in.
      </p>
      <div className="as-field">
        <label className="as-label" htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" className="as-input" required
               autoComplete="current-password" value={current}
               onChange={(e) => setCurrent(e.target.value)} />
      </div>
      <div className="as-field">
        <label className="as-label" htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" className="as-input" required
               autoComplete="new-password" value={next} aria-invalid={tooShort || undefined}
               aria-describedby="pw-new-help" onChange={(e) => setNext(e.target.value)} />
        <p id="pw-new-help" className="as-help">
          At least {MIN_PASSWORD} characters. A short sentence is easier to remember than a code.
        </p>
      </div>
      <div className="as-field">
        <label className="as-label" htmlFor="pw-repeat">New password again</label>
        <input id="pw-repeat" type="password" className="as-input" required
               autoComplete="new-password" value={repeat} aria-invalid={mismatch || undefined}
               onChange={(e) => setRepeat(e.target.value)} />
        {mismatch && <p className="as-help as-help-error">Does not match the new password yet.</p>}
      </div>
      {error && <div className="as-warn" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
      {done && <div className="as-note" role="status" style={{ marginBottom: 12 }}>Password changed.</div>}
      <button className="as-btn" data-busy={busy} disabled={busy}>
        {busy ? 'Changing…' : 'Change password'}
      </button>
    </form>
  )
}

export default function Account() {
  const { user } = useAuth()
  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Account"
        icon={KeyRound}
        title="Your account"
        description="Who you are signed in as, and your password."
      />
      <div className="as-account-grid">
        <section className="as-card plain">
          <h2>Signed in as</h2>
          <dl className="as-account-facts">
            <dt>Name</dt><dd>{user?.name}</dd>
            <dt>Role</dt><dd>{ROLE_TEXT[user?.role] || user?.role}</dd>
            <dt>Barangay</dt><dd>{user?.barangay || 'Not set'}</dd>
          </dl>
          <p className="as-muted" style={{ fontSize: 13, margin: 0 }}>
            Only an administrator can change your name, role or barangay.
          </p>
        </section>
        <ChangePasswordForm />
      </div>
    </div>
  )
}
