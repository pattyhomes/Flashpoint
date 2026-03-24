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
  // Prefer backend's last_computed_at (authoritative data freshness).
  // Backend emits naive UTC — append 'Z' so JS parses it as UTC, not local time.
  const computedAt = systemStatus?.last_computed_at
    ? new Date(systemStatus.last_computed_at + 'Z')
    : null

  const displayDate = computedAt ?? lastUpdated

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
            {systemStatus?.is_stale && (
              <span className="status-bar__stale">Stale data</span>
            )}
          </>
      }
    </div>
  )
}
