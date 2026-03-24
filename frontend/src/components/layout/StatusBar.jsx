function relativeTime(date) {
  if (!date) return null
  const sec = Math.floor((Date.now() - date.getTime()) / 1000)
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

export default function StatusBar({ lastUpdated, loading, systemStatus }) {
  // Backend emits naive UTC strings (no 'Z') — append 'Z' to force UTC parsing in JS.
  // Prefer last_success_at (run freshness) over last_computed_at (compute freshness).
  const successAt  = systemStatus?.last_success_at  ? new Date(systemStatus.last_success_at  + 'Z') : null
  const computedAt = systemStatus?.last_computed_at ? new Date(systemStatus.last_computed_at + 'Z') : null
  const displayDate = successAt ?? computedAt ?? lastUpdated

  const isRunning = systemStatus?.last_run_status === 'running'
  // SYNCING and RUN FAILED are mutually exclusive — SYNCING takes precedence
  const isFailed  = !isRunning && systemStatus?.last_run_status === 'failed'
  const isStale   = systemStatus?.is_stale === true

  const errorText = isFailed && systemStatus?.last_error
    ? systemStatus.last_error.slice(0, 48) + (systemStatus.last_error.length > 48 ? '…' : '')
    : null

  return (
    <div className="status-bar">
      <span className="status-bar__name">Flashpoint</span>
      <span className="status-bar__sep" />
      {loading
        ? <span className="status-bar__loading">Loading…</span>
        : <>
            <span className="status-bar__updated">
              {displayDate ? `Updated ${relativeTime(displayDate)}` : '—'}
            </span>
            {systemStatus && (
              <span className="status-bar__counts">
                {systemStatus.event_count} EVT · {systemStatus.hotspot_count} HS
              </span>
            )}
            <span className="status-bar__badges">
              {isStale && (
                <span className="status-bar__badge status-bar__badge--stale">
                  <span className="status-bar__badge-dot" />
                  STALE
                </span>
              )}
              {isFailed && (
                <span className="status-bar__badge status-bar__badge--failed">
                  <span className="status-bar__badge-dot" />
                  RUN FAILED{errorText && `: ${errorText}`}
                </span>
              )}
              {isRunning && (
                <span className="status-bar__badge status-bar__badge--syncing">
                  <span className="status-bar__badge-dot" />
                  SYNCING
                </span>
              )}
            </span>
          </>
      }
    </div>
  )
}
