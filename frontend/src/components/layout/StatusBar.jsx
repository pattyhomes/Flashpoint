function relativeTime(date) {
  if (!date) return null
  const sec = Math.floor((Date.now() - date.getTime()) / 1000)
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

export default function StatusBar({ lastUpdated, loading }) {
  return (
    <div className="status-bar">
      <span className="status-bar__name">Flashpoint</span>
      <span className="status-bar__sep" />
      {loading
        ? <span className="status-bar__loading">Loading…</span>
        : <span className="status-bar__updated">
            {lastUpdated ? `Updated ${relativeTime(lastUpdated)}` : '—'}
          </span>
      }
    </div>
  )
}
