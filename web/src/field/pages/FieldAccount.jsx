import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../state/auth'
import { ChangePasswordForm } from '../../pages/Account'
import { Bi } from '../labels'

export default function FieldAccount() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  return (
    <div className="fc-account">
      <h1 style={{ fontSize: 20 }}><Bi k="account" /></h1>
      <div className="fc-card">
        <div className="fc-account-name">{user?.name}</div>
        <div className="fc-account-meta">{user?.barangay || 'Barangay not set'}</div>
      </div>
      <ChangePasswordForm compact />
      <button type="button" className="as-btn secondary block fc-account-signout"
              onClick={() => { signOut(); navigate('/login') }}>
        Sign out
      </button>
    </div>
  )
}
