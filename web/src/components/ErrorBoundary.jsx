import { Component } from 'react'

/* After a redeploy, an open tab still refers to the previous build's chunk files, which
   no longer exist. The first navigation to a lazy page then fails to load its module.
   That is not a bug in the page: reloading fetches the new build. Done once per tab, so
   a chunk that is genuinely broken cannot cause a reload loop. */
const RELOAD_FLAG = 'agriscan_chunk_reload'

export function isChunkLoadError(error) {
  const text = `${error?.name || ''} ${error?.message || ''}`
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk \d+ failed/i.test(text)
}

export function reloadOnceForNewBuild() {
  try {
    if (sessionStorage.getItem(RELOAD_FLAG)) return false
    sessionStorage.setItem(RELOAD_FLAG, String(Date.now()))
  } catch {
    return false
  }
  window.location.reload()
  return true
}

export function clearReloadFlag() {
  try { sessionStorage.removeItem(RELOAD_FLAG) } catch { /* private mode */ }
}

/* A rendering error in one page used to blank the whole app, with nothing on screen to
   report. This shows what failed, keeps a way out, and gives the exact text to send. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, copied: false }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    if (isChunkLoadError(error) && reloadOnceForNewBuild()) return
    // Kept in the console for F12 > Console, with the component stack.
    console.error('AGRISCAN page error:', error, info?.componentStack)
    this.componentStack = info?.componentStack || ''
  }

  details() {
    const { error } = this.state
    return [
      `Page: ${window.location.pathname}`,
      `Time: ${new Date().toISOString()}`,
      `Browser: ${navigator.userAgent}`,
      `Error: ${error?.name || 'Error'}: ${error?.message || String(error)}`,
      (error?.stack || '').split('\n').slice(0, 6).join('\n'),
      (this.componentStack || '').trim().split('\n').slice(0, 6).join('\n'),
    ].join('\n')
  }

  async copy() {
    try {
      await navigator.clipboard.writeText(this.details())
      this.setState({ copied: true })
    } catch {
      this.setState({ copied: false })
    }
  }

  render() {
    const { error, copied } = this.state
    if (!error) return this.props.children
    const chunk = isChunkLoadError(error)
    return (
      <div className="as-crash" role="alert">
        <div className="as-crash-card">
          <h1>{chunk ? 'AGRISCAN was updated' : 'This page stopped working'}</h1>
          <p>
            {chunk
              ? 'A newer version is on the server. Reload to continue; nothing you saved is lost.'
              : 'The rest of the system is fine, and nothing was saved or changed by this error. Reload the page, or go back to the overview.'}
          </p>
          <div className="as-crash-actions">
            <button className="as-btn" onClick={() => { clearReloadFlag(); window.location.reload() }}>
              Reload page
            </button>
            <a className="as-btn secondary" href="/">Go to overview</a>
          </div>
          {!chunk && (
            <details className="as-crash-details">
              <summary>Details to send to the team</summary>
              <pre>{this.details()}</pre>
              <button className="as-btn secondary" onClick={() => this.copy()}>
                {copied ? 'Copied' : 'Copy details'}
              </button>
            </details>
          )}
        </div>
      </div>
    )
  }
}
