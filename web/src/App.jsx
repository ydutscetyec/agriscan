import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import Splash from './components/Splash'
import { OnboardingProvider } from './components/Onboarding'
import { useAuth } from './state/auth'
import Login from './pages/Login'
import Detections from './pages/Detections'
import Recommendations from './pages/Recommendations'
import Account from './pages/Account'
import Captures from './pages/Captures'
const FieldApp = lazy(() => import('./field/FieldApp'))
const VerificationQueue = lazy(() => import('./pages/VerificationQueue'))
const Upload = lazy(() => import('./pages/Upload'))
const Analytics = lazy(() => import('./pages/Analytics'))
const DroneCamera = lazy(() => import('./pages/DroneCamera'))
const FieldBoundaries = lazy(() => import('./pages/FieldBoundaries'))
const CameraStation = lazy(() => import('./pages/CameraStation'))
const DroneModel = lazy(() => import('./pages/DroneModel'))

/* Leaflet and Chart.js are the two heavy dependencies. Loading them only when their
   page is opened keeps the first paint small on a field technician's laptop. */
const Home = lazy(() => import('./pages/Home'))
const Fields = lazy(() => import('./pages/Fields'))
const MapPage = lazy(() => import('./pages/MapPage'))
import DetectionDetail from './pages/DetectionDetail'
import Missions from './pages/Missions'
import Models from './pages/Models'
import { Farmers, Users } from './pages/People'

/* Farmers get the field client, not the dashboard: the sidebar and data tables are
   built for a technician at a desk. */
function RequireField({ children }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <p className="as-content as-muted">Checking your session…</p>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  return <Suspense fallback={<p className="as-content as-muted">Loading…</p>}>{children}</Suspense>
}

/* The drone camera station: technicians and admins only, and no sidebar. */
function RequireStation({ children }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <p className="as-content as-muted">Checking your session…</p>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (!['admin', 'technician'].includes(user.role)) {
    return (
      <div className="as-content">
        <div className="as-warn">
          The drone camera needs a technician or admin account. You are signed in as {user.role}.
        </div>
      </div>
    )
  }
  return <Suspense fallback={<p className="as-content as-muted">Loading…</p>}>{children}</Suspense>
}

function RequireAuth({ children, roles }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <p className="as-content as-muted">Checking your session…</p>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (roles && !roles.includes(user.role)) {
    return (
      <AppShell>
        <div className="as-content">
          <div className="as-warn">
            Your role ({user.role}) does not have access to this page.
          </div>
        </div>
      </AppShell>
    )
  }
  return (
    <AppShell>
      <Suspense fallback={<p className="as-content as-muted">Loading…</p>}>{children}</Suspense>
    </AppShell>
  )
}

/** A farmer signing in lands in the field client; everyone else on the dashboard. */
function HomeOrField() {
  const { user, checking } = useAuth()
  if (checking) return <p className="as-content as-muted">Checking your session…</p>
  if (user && user.role === 'farmer') return <Navigate to="/field" replace />
  return (
    <RequireAuth>
      <Home />
    </RequireAuth>
  )
}

/** Farmers manage their account inside the field client, everyone else in the dashboard. */
function AccountRoute() {
  const { user } = useAuth()
  if (user && user.role === 'farmer') return <Navigate to="/field/account" replace />
  return <RequireAuth><Account /></RequireAuth>
}

export default function App() {
  return (
    <>
      {/* Overlays whatever route is loading underneath; it never gates it. */}
      <Splash />
      <OnboardingProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/field/*" element={<RequireField><FieldApp /></RequireField>} />
        {/* The phone mounted on the drone. Full screen, no dashboard chrome. */}
        <Route path="/camera" element={<RequireStation><CameraStation /></RequireStation>} />
        <Route path="/" element={<HomeOrField />} />
        <Route path="/map" element={<RequireAuth><MapPage /></RequireAuth>} />
        <Route path="/detections" element={<RequireAuth><Detections /></RequireAuth>} />
        <Route path="/detections/:id" element={<RequireAuth><DetectionDetail /></RequireAuth>} />
        <Route
          path="/verify"
          element={
            <RequireAuth roles={['admin', 'technician', 'researcher']}>
              <VerificationQueue />
            </RequireAuth>
          }
        />
        <Route
          path="/recommendations"
          element={
            <RequireAuth roles={['admin', 'technician', 'researcher']}>
              <Recommendations />
            </RequireAuth>
          }
        />
        <Route
          path="/upload"
          element={
            <RequireAuth roles={['admin', 'technician', 'researcher']}>
              <Upload />
            </RequireAuth>
          }
        />
        <Route
          path="/analytics"
          element={
            <RequireAuth roles={['admin', 'technician', 'researcher']}>
              <Analytics />
            </RequireAuth>
          }
        />
        <Route
          path="/drone-camera"
          element={<RequireAuth roles={['admin', 'technician']}><DroneCamera /></RequireAuth>}
        />
        <Route path="/aircraft" element={<RequireAuth><DroneModel /></RequireAuth>} />
        <Route path="/field-boundaries" element={<RequireAuth><FieldBoundaries /></RequireAuth>} />
        <Route path="/fields" element={<RequireAuth><Fields /></RequireAuth>} />
        <Route path="/missions" element={<RequireAuth><Missions /></RequireAuth>} />
        <Route path="/captures" element={<RequireAuth><Captures /></RequireAuth>} />
        <Route
          path="/farmers"
          element={<RequireAuth roles={['admin', 'technician', 'researcher']}><Farmers /></RequireAuth>}
        />
        <Route path="/models" element={<RequireAuth><Models /></RequireAuth>} />
        <Route path="/users" element={<RequireAuth roles={['admin']}><Users /></RequireAuth>} />
        <Route path="/account" element={<AccountRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </OnboardingProvider>
    </>
  )
}
