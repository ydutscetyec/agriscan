import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3, Bot, Camera, ClipboardCheck, Cpu, LayoutDashboard, LogOut, Map, MapPinned,
  HelpCircle, Images, Menu, MessageSquareText, Plane, ScanSearch, Sprout, Upload, Users,
  UsersRound, X,
} from 'lucide-react'
import { useAuth } from '../state/auth'
import ErrorBoundary from './ErrorBoundary'
import { useTour } from './Onboarding'
import { BrandMark } from './Layout'
import SystemStatus from './SystemStatus'

/* Navigation covers only subsystems with a real data source. There is deliberately no
   entry for 3D terrain, irrigation, soil or outbreak risk: nothing feeds them yet, and
   an empty page invites a question the system cannot answer. */
const OPERATORS = ['admin', 'technician', 'researcher']

const GROUPS = [
  {
    label: 'Monitoring',
    items: [
      { to: '/map', label: 'Map', icon: Map },
      { to: '/detections', label: 'Detections', icon: ScanSearch },
      { to: '/verify', label: 'Verification queue', icon: ClipboardCheck, roles: OPERATORS },
      { to: '/recommendations', label: 'Recommendations', icon: MessageSquareText, roles: OPERATORS },
    ],
  },
  {
    label: 'Capture',
    items: [
      { to: '/drone-camera', label: 'Drone camera', icon: Camera, roles: ['admin', 'technician'] },
      { to: '/captures', label: 'Captured images', icon: Images },
      { to: '/missions', label: 'Flight records', icon: Plane },
      { to: '/aircraft', label: 'The aircraft', icon: Bot },
      { to: '/upload', label: 'Upload images', icon: Upload, roles: OPERATORS },
    ],
  },
  {
    label: 'Fields',
    items: [
      { to: '/field-boundaries', label: 'Field boundaries', icon: MapPinned },
      { to: '/fields', label: 'Manage fields', icon: Sprout },
      { to: '/farmers', label: 'Farmers', icon: UsersRound, roles: OPERATORS },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { to: '/analytics', label: 'Analytics', icon: BarChart3, roles: OPERATORS },
    ],
  },
  {
    label: 'Administration',
    items: [
      { to: '/models', label: 'Models', icon: Cpu },
      { to: '/users', label: 'Users', icon: Users, roles: ['admin'] },
    ],
  },
]

function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
}

export default function AppShell({ children }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Below 900 px the sidebar is a drawer. A technician arming the drone camera from a
  // phone in the field had about 140 px of page beside a fixed 236 px sidebar.
  const [menuOpen, setMenuOpen] = useState(false)
  const tour = useTour()

  useEffect(() => { setMenuOpen(false) }, [location.pathname])
  useEffect(() => {
    if (!menuOpen) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const operator = user && OPERATORS.includes(user.role)

  return (
    <div className={`as-shell${menuOpen ? ' menu-open' : ''}`}>
      <nav className="as-sidebar" id="as-sidebar" aria-label="Main">
        <div className="as-brand">
          <NavLink to="/" style={{ color: 'inherit', display: 'flex', alignItems: 'center', gap: 10 }}>
            <BrandMark />
            <div>
              <div className="as-brand-name">AGRISCAN</div>
              <div className="as-brand-sub">Philippine rice intelligence</div>
            </div>
          </NavLink>
          <button type="button" className="as-menu-close" aria-label="Close menu"
                  onClick={() => setMenuOpen(false)}>
            <X size={20} strokeWidth={1.75} />
          </button>
        </div>

        <NavLink to="/" end className="as-navlink">
          <LayoutDashboard size={18} strokeWidth={1.75} /> Overview
        </NavLink>

        {GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !item.roles || (user && item.roles.includes(user.role)),
          )
          if (!items.length) return null
          return (
            <div className="as-navgroup" key={group.label}>
              <div className="as-navgroup-label">{group.label}</div>
              {items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} className="as-navlink">
                  <Icon size={18} strokeWidth={1.75} /> {label}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>
      <div className="as-scrim" aria-hidden="true" onClick={() => setMenuOpen(false)} />

      <div className="as-main">
        <header className="as-topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <button type="button" className="as-menu-button" aria-label="Open menu"
                    aria-controls="as-sidebar" aria-expanded={menuOpen}
                    onClick={() => setMenuOpen(true)}>
              <Menu size={20} strokeWidth={1.75} />
            </button>
            <div className="as-topbar-place">Surallah, South Cotabato</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <button type="button" className="as-iconbtn" onClick={tour.start}
                    title="Show the guide for your role" aria-label="Show the guide">
              <HelpCircle size={19} strokeWidth={1.75} />
            </button>
            <Link to="/account" className="as-userchip" title="Your account and password">
              <div className="as-avatar" aria-hidden="true">{initials(user?.name)}</div>
              <div className="as-userchip-text">
                <div className="as-userchip-name">{user?.name}</div>
                <div className="as-userchip-role">{user?.role}</div>
              </div>
            </Link>
            <button
              className="as-btn secondary"
              onClick={() => { signOut(); navigate('/login') }}
            >
              <LogOut size={16} strokeWidth={1.75} /> <span className="as-signout-text">Sign out</span>
            </button>
          </div>
        </header>
        {operator && <SystemStatus />}
        {/* Keyed by path, so a page that crashed recovers when you navigate away. */}
        <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>
      </div>
    </div>
  )
}
