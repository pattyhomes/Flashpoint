import { parseUTC, relativeTimeAgo } from '../../utils/time'

export default function StatusBar({ lastUpdated, loading, systemStatus }) {
  // parseUTC handles naive UTC strings from the backend (no 'Z' suffix).
  const successAt  = parseUTC(systemStatus?.last_success_at)
  const computedAt = parseUTC(systemStatus?.last_computed_at)
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
              {displayDate ? `Updated ${relativeTimeAgo(displayDate)}` : '—'}
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
