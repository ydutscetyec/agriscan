import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../state/auth'
import { BrandMark } from '../components/Layout'

export default function Login() {
  const { signIn, endedReason } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await signIn(name, password)
      navigate(location.state?.from?.pathname || '/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="as-login">
      <aside className="as-login-panel">
        <div className="as-login-brand">
          <BrandMark size={34} />
          <div>
            <div className="as-login-name">AGRISCAN</div>
            <div className="as-login-sub">Philippine rice intelligence</div>
          </div>
        </div>

        <div className="as-login-pitch">
          <h1>Rice field monitoring for Surallah</h1>
          <p>
            Drone and phone images, checked by an agricultural technician before any
            advice reaches a farmer. The system reports what it found and how sure it
            is, never more than that.
          </p>
        </div>

      </aside>

      <main className="as-login-form">
        <form className="as-login-card as-card plain" onSubmit={submit}>
          <h2>Sign in</h2>
          <p className="as-login-hint">Use the account your adviser or administrator set up.</p>

          <div className="as-field">
            <label className="as-label" htmlFor="name">Name</label>
            <input id="name" className="as-input" value={name} autoFocus
                   onChange={(e) => setName(e.target.value)}
                   autoComplete="username" required />
          </div>

          <div className="as-field">
            <label className="as-label" htmlFor="pw">Password</label>
            <input id="pw" type="password" className="as-input" value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   autoComplete="current-password" required />
          </div>

          {!error && endedReason && (
            <div className="as-note" style={{ marginBottom: 12 }} role="status">{endedReason}</div>
          )}
          {error && (
            <div className="as-warn" style={{ marginBottom: 12 }} role="alert">{error}</div>
          )}

          <button className="as-btn block" data-busy={busy} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </main>
    </div>
  )
}
