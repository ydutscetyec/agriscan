import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Users as UsersIcon } from 'lucide-react'
import { api } from '../api/client'
import { PageHeader } from '../components/Layout'
import { useAuth } from '../state/auth'

function PeopleTable({ rows, showRole }) {
  if (rows.length === 0) return <div className="as-empty">No accounts to show.</div>
  return (
    <table className="as-table">
      <thead>
        <tr><th>Name</th>{showRole && <th>Role</th>}<th>Barangay</th><th>Status</th></tr>
      </thead>
      <tbody>
        {rows.map((u) => (
          <tr key={u.id}>
            <td>{u.name}</td>
            {showRole && <td>{u.role}</td>}
            <td>{u.barangay || '—'}</td>
            <td>
              {u.is_demo && <span className="as-muted">Demo account</span>}
              {u.active === false && <span style={{ color: 'var(--sev-severe)' }}> Inactive</span>}
              {!u.is_demo && u.active !== false && '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Farmers() {
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  useEffect(() => { api.farmers().then(setRows).catch((e) => setError(e.message)) }, [])
  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Fields"
        icon={UsersIcon} title="Farmers" description="Accounts that own farms and fields in the system." />
      {error && <div className="as-warn">{error}</div>}
      <PeopleTable rows={rows} showRole={false} />
    </div>
  )
}

const EMPTY_USER = { name: '', role: 'farmer', barangay: '', password: '' }
const MIN_PASSWORD = 10
const ROLE_OPTIONS = [
  ['farmer', 'Farmer'], ['technician', 'Technician'], ['researcher', 'Researcher'], ['admin', 'Admin'],
]

/** One account row with its actions. Every action is checked again on the server. */
function UserRow({ row, me, onChanged }) {
  const [resetting, setResetting] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const isMe = row.id === me?.id

  async function run(action, success) {
    if (busy) return
    setBusy(true)
    setMessage(null)
    try {
      await action()
      setMessage({ ok: true, text: success })
      onChanged()
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  function changeRole(role) {
    if (role === row.role) return
    if (role === 'technician' && !window.confirm(
      `Make ${row.name} a technician? Technicians approve the advice farmers act on.`)) return
    run(() => api.updateUser(row.id, { role }), `Role changed to ${role}.`)
  }

  function toggleActive() {
    const next = !row.active
    if (!next && !window.confirm(`Deactivate ${row.name}? They are signed out at once and cannot sign in until reactivated. Their data is kept.`)) return
    run(() => api.updateUser(row.id, { active: next }), next ? 'Reactivated.' : 'Deactivated.')
  }

  function submitReset(event) {
    event.preventDefault()
    if (password.length < MIN_PASSWORD) {
      setMessage({ ok: false, text: `At least ${MIN_PASSWORD} characters.` })
      return
    }
    run(async () => {
      await api.resetPassword(row.id, password)
      setPassword('')
      setResetting(false)
    }, `New password set. ${row.name} is signed out everywhere; give them the password in person.`)
  }

  return (
    <>
      <tr className={row.active === false ? 'as-row-inactive' : undefined}>
        <td>
          <div style={{ fontWeight: 600 }}>{row.name}{isMe && <span className="as-muted"> (you)</span>}</div>
          {row.is_demo && <div className="as-muted" style={{ fontSize: 12 }}>Demo account</div>}
        </td>
        <td>
          {isMe ? (
            <span style={{ textTransform: 'capitalize' }}>{row.role}</span>
          ) : (
            <select className="as-select as-select-sm" value={row.role} disabled={busy}
                    aria-label={`Role for ${row.name}`} onChange={(e) => changeRole(e.target.value)}>
              {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          )}
        </td>
        <td>{row.barangay || '—'}</td>
        <td>
          {row.active === false
            ? <span className="as-state-off">Inactive</span>
            : <span className="as-state-on">Active</span>}
        </td>
        <td className="as-row-actions">
          {!isMe && (
            <>
              <button type="button" className="as-btn secondary as-btn-sm" disabled={busy}
                      onClick={() => { setResetting((v) => !v); setMessage(null) }}>
                Reset password
              </button>
              <button type="button" className="as-btn secondary as-btn-sm" disabled={busy}
                      onClick={toggleActive}>
                {row.active === false ? 'Reactivate' : 'Deactivate'}
              </button>
            </>
          )}
          {isMe && <Link to="/account" style={{ fontSize: 13 }}>Change your password</Link>}
        </td>
      </tr>
      {(resetting || message) && (
        <tr className="as-row-detail">
          <td colSpan={5}>
            {resetting && (
              <form className="as-inline-form" onSubmit={submitReset}>
                <label className="as-label" htmlFor={`reset-${row.id}`}>New password for {row.name}</label>
                <input id={`reset-${row.id}`} type="password" className="as-input" autoComplete="new-password"
                       value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
                <button className="as-btn as-btn-sm" disabled={busy}>Set password</button>
                <button type="button" className="as-btn secondary as-btn-sm"
                        onClick={() => { setResetting(false); setPassword('') }}>Cancel</button>
              </form>
            )}
            {message && (
              <div className={message.ok ? 'as-note' : 'as-warn'} role="status" style={{ marginTop: resetting ? 8 : 0 }}>
                {message.text}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export function Users() {
  const { user: me } = useAuth()
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(EMPTY_USER)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showInactive, setShowInactive] = useState(true)

  const reload = () => api.users().then(setRows).catch((e) => setError(e.message))
  useEffect(() => { reload() }, [])

  const passwordShort = form.password.length > 0 && form.password.length < MIN_PASSWORD
  const visible = showInactive ? rows : rows.filter((r) => r.active !== false)
  const activeCount = rows.filter((r) => r.active !== false).length

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setError(null)
    setNotice(null)
    if (form.password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`)
      return
    }
    setBusy(true)
    try {
      const created = await api.createUser({
        name: form.name.trim(),
        role: form.role,
        barangay: form.barangay.trim() || null,
        password: form.password,
      })
      setNotice(`Created ${created.name} (${created.role}). Share the password in person, not by message.`)
      setForm(EMPTY_USER)
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Administration"
        icon={UsersIcon}
        title="Users"
        description="All accounts and their roles. Roles are enforced on the server; changing what a page shows never changes what an account may do."
        meta={rows.length ? `${activeCount} active of ${rows.length}` : null}
      />

      <form className="as-card plain" onSubmit={submit} style={{ marginBottom: 24, maxWidth: 720 }}>
        <h2>Add an account</h2>
        <div className="as-grid cols-2">
          <div className="as-field">
            <label className="as-label" htmlFor="nu-name">Name</label>
            <input id="nu-name" className="as-input" required value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="as-field">
            <label className="as-label" htmlFor="nu-role">Role</label>
            <select id="nu-role" className="as-select" value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="farmer">Farmer — field client, own farm only</option>
              <option value="technician">Technician — verifies and approves advice</option>
              <option value="researcher">Researcher — data and analysis</option>
              <option value="admin">Admin — accounts and settings</option>
            </select>
          </div>
          <div className="as-field">
            <label className="as-label" htmlFor="nu-brgy">Barangay</label>
            <input id="nu-brgy" className="as-input" value={form.barangay}
                   onChange={(e) => setForm({ ...form, barangay: e.target.value })} />
          </div>
          <div className="as-field">
            <label className="as-label" htmlFor="nu-pw">Initial password</label>
            <input id="nu-pw" type="password" className="as-input" required
                   autoComplete="new-password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <p className="as-muted" style={{ fontSize: 12, margin: '4px 0 0', color: passwordShort ? 'var(--sev-severe)' : undefined }}>
              At least {MIN_PASSWORD} characters. They can change it under their account.
            </p>
          </div>
        </div>
        {form.role === 'technician' && (
          <div className="as-warn" style={{ marginBottom: 12 }}>
            Technicians approve the advice farmers act on. Only give this role to a
            qualified agricultural technician.
          </div>
        )}
        {error && <div className="as-warn" style={{ marginBottom: 12 }}>{error}</div>}
        {notice && <div className="as-note" style={{ marginBottom: 12 }}>{notice}</div>}
        <button className="as-btn" data-busy={busy} disabled={busy}>{busy ? 'Creating…' : 'Create account'}</button>
      </form>

      <div className="as-table-toolbar">
        <label className="as-check">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show inactive accounts
        </label>
      </div>
      {visible.length === 0 ? (
        <div className="as-empty">No accounts to show.</div>
      ) : (
        <div className="as-table-scroll">
          <table className="as-table">
            <thead>
              <tr><th>Name</th><th>Role</th><th>Barangay</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {visible.map((row) => <UserRow key={row.id} row={row} me={me} onChanged={reload} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
