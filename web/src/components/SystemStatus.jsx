import { useEffect, useState } from 'react'
import { api } from '../api/client'

const POLL_MS = 60_000

function minutes(seconds) {
  const m = Math.round((seconds || 0) / 60)
  return m <= 1 ? 'a minute' : `${m} minutes`
}

/* Shown to operators only, and only when something needs doing. A permanent green
   "all systems normal" strip would be decoration; this says what is wrong and what to
   check. The worker is a separate program from the website, so the website can look
   fine while nothing is being analysed. */
export function statusMessage(health) {
  if (!health) return null
  if (health.database === 'unreachable') {
    return {
      level: 'warn',
      text: 'The server cannot reach its database. Nothing can be saved. On the laptop server, check that MySQL is running in XAMPP.',
    }
  }
  const q = health.queue || {}
  if (q.stalled) {
    const noModel = health.model === 'MODEL_NOT_AVAILABLE'
    return {
      level: 'warn',
      text: noModel
        ? `${q.waiting} photo${q.waiting === 1 ? ' is' : 's are'} waiting for analysis, the oldest for ${minutes(q.oldest_waiting_seconds)}. No model is in production yet, so they will wait until one is registered.`
        : `${q.waiting} photo${q.waiting === 1 ? ' is' : 's are'} waiting for analysis, the oldest for ${minutes(q.oldest_waiting_seconds)}, and nothing is running. Check that the worker (python -m worker.run) is open on the server.`,
    }
  }
  if (q.failed_last_24h > 0) {
    return {
      level: 'note',
      text: `${q.failed_last_24h} photo${q.failed_last_24h === 1 ? '' : 's'} failed analysis in the last 24 hours. The worker log says why.`,
    }
  }
  return null
}

export default function SystemStatus() {
  const [health, setHealth] = useState(null)
  const [unreachable, setUnreachable] = useState(false)

  useEffect(() => {
    let alive = true
    const check = () =>
      api.health()
        .then((h) => { if (alive) { setHealth(h); setUnreachable(false) } })
        .catch((err) => {
          if (!alive) return
          // 503 from /health carries a body saying the database is down.
          if (/database/i.test(err.message)) setHealth({ database: 'unreachable' })
          else setUnreachable(true)
        })
    check()
    const id = setInterval(check, POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const message = unreachable
    ? { level: 'warn', text: 'Cannot reach the AGRISCAN server. Changes will fail until it is back.' }
    : statusMessage(health)
  if (!message) return null
  return (
    <div className={`as-status ${message.level}`} role="status">
      {message.text}
    </div>
  )
}
