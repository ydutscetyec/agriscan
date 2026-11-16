import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import ErrorBoundary, { clearReloadFlag, reloadOnceForNewBuild } from './components/ErrorBoundary'
import { AuthProvider } from './state/auth'
// Inter is bundled, not fetched from Google Fonts: the server may be a laptop with no
// internet, and the field client must open with no signal. Latin covers English,
// Hiligaynon and Filipino (ñ included).
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import 'leaflet/dist/leaflet.css'
import './styles/tokens.css'
import './styles/app.css'

// Vite raises this when a lazy page's file is gone after a redeploy. Reload once to get
// the new build instead of failing on the old one.
window.addEventListener('vite:preloadError', (event) => {
  if (reloadOnceForNewBuild()) event.preventDefault()
})
// A successful start means any earlier reload did its job.
window.addEventListener('load', () => setTimeout(clearReloadFlag, 10000))

// The field client must open with no signal, so production builds register the
// service worker. Development must NOT: a worker serving cached source modules makes an
// updated app look unchanged. Any worker left over from an earlier session is removed.
if ('serviceWorker' in navigator) {
  if (import.meta.env.PROD) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {})
    })
  } else {
    navigator.serviceWorker.getRegistrations()
      .then((regs) => regs.forEach((r) => r.unregister()))
      .catch(() => {})
    if (window.caches) {
      caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {})
    }
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      {/* Opt in to React Router v7 behaviour now. Every link in the app is absolute, so
          neither flag changes where anything goes; it silences the upgrade warnings. */}
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
)
