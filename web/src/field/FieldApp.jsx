import { useCallback, useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import FieldShell from './FieldShell'
import Capture from './pages/Capture'
import Results from './pages/Results'
import ResultDetail from './pages/ResultDetail'
import FieldAccount from './pages/FieldAccount'
import { STATE, allCaptures } from './db'
import { startSync } from './sync'
import { uploadCapture as uploader } from './uploader'


export default function FieldApp() {
  const [pending, setPending] = useState(0)
  const [online, setOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  )
  const [refreshKey, setRefreshKey] = useState(0)

  const recount = useCallback(async () => {
    const rows = await allCaptures().catch(() => [])
    setPending(rows.filter((r) => r.state !== STATE.SYNCED).length)
  }, [])

  useEffect(() => {
    recount()
    const stop = startSync(uploader, {
      onChange: () => {
        recount()
        setRefreshKey((k) => k + 1)
      },
    })
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      stop()
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [recount])

  return (
    <FieldShell pending={pending} online={online}>
      <Routes>
        <Route index element={<Capture onQueued={recount} online={online} />} />
        <Route path="results" element={<Results refreshKey={refreshKey} />} />
        <Route path="results/:id" element={<ResultDetail />} />
        <Route path="account" element={<FieldAccount />} />
      </Routes>
    </FieldShell>
  )
}
