import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../state/auth'
import { Camera, ClipboardList, HelpCircle, UserRound } from 'lucide-react'
import { useTour } from '../components/Onboarding'
import { Bi } from './labels'

/* A separate shell from the dashboard: one thumb, two destinations, large targets.
   The technician sidebar would be unusable on a phone in a paddy. */
export default function FieldShell({ children, pending, online }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const tour = useTour()

  return (
    <div className="fc-shell">
      <header className="fc-top">
        <Link to="/field/account" className="fc-account-link" aria-label="My account">
          <div className="fc-brand">AGRISCAN</div>
          <div className="fc-user">
            <UserRound size={13} strokeWidth={2} aria-hidden="true" /> {user?.name}
          </div>
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {!online && <span className="fc-pill offline">No signal</span>}
          <button type="button" className="fc-help" onClick={tour.start}
                  aria-label="Show the guide">
            <HelpCircle size={20} strokeWidth={1.9} />
          </button>
          {pending > 0 && <span className="fc-pill">{pending} waiting</span>}
          <button
            className="as-btn ghost fc-signout"
            onClick={() => { signOut(); navigate('/login') }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="fc-main">{children}</main>

      <nav className="fc-tabs">
        <NavLink to="/field" end
                 className={({ isActive }) => `fc-tab${isActive ? ' active' : ''}`}>
          <Camera size={22} strokeWidth={1.9} aria-hidden="true" />
          <Bi k="capture" />
        </NavLink>
        <NavLink to="/field/results"
                 className={({ isActive }) => `fc-tab${isActive ? ' active' : ''}`}>
          <ClipboardList size={22} strokeWidth={1.9} aria-hidden="true" />
          <Bi k="myResults" />
        </NavLink>
      </nav>
    </div>
  )
}
