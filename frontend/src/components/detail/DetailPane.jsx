import { useRef, useEffect } from 'react'

function severityColor(score) {
  if (score >= 0.8) return '#ef4444'
  if (score >= 0.6) return '#f59e0b'
  if (score >= 0.4) return '#eab308'
  return '#22c55e'
}

function ScoreBar({ label, value }) {
  return (
    <div className="score-bar-row">
      <span className="score-bar-row__label">{label}</span>
      <div className="score-bar">
        <div
          className="score-bar__fill"
          style={{ width: `${value * 100}%`, backgroundColor: severityColor(value) }}
        />
      </div>
      <span className="score-bar-row__val">{Math.round(value * 100)}</span>
    </div>
  )
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function badgeStyle(type) {
  const colors = {
    violence:   { color: '#ef4444', border: 'rgba(239,68,68,0.4)' },
    unrest:     { color: '#f59e0b', border: 'rgba(245,158,11,0.4)' },
    disruption: { color: '#eab308', border: 'rgba(234,179,8,0.4)' },
    protest:    { color: '#22c55e', border: 'rgba(34,197,94,0.4)' },
  }
  const c = colors[type] || { color: '#9aa0b0', border: 'rgba(154,160,176,0.4)' }
  return { color: c.color, borderColor: c.border }
}

function EventDetail({ event }) {
  const location = [event.city, event.state].filter(Boolean).join(', ') || event.country
  return (
    <div className="detail-body">
      <div className="detail-title">{event.title}</div>

      <div className="detail-row">
        <span className="detail-row__label">Type</span>
        <span
          className="detail-badge"
          style={badgeStyle(event.event_type)}
        >
          {event.event_type}
        </span>
      </div>

      <div className="detail-meta">
        <div className="detail-row">
          <span className="detail-row__label">Location</span>
          <span className="detail-row__value detail-row__value--primary">{location}</span>
        </div>
        <div className="detail-row">
          <span className="detail-row__label">Occurred</span>
          <span className="detail-row__value">{formatDate(event.occurred_at)}</span>
        </div>
        {event.trend_state && (
          <div className="detail-row">
            <span className="detail-row__label">Trend</span>
            <span className="detail-row__value">{event.trend_state}</span>
          </div>
        )}
        <div className="detail-row">
          <span className="detail-row__label">Source</span>
          <span className="detail-row__value">{event.source_name}</span>
        </div>
        {event.source_count > 1 && (
          <div className="detail-row">
            <span className="detail-row__label">Sources</span>
            <span className="detail-row__value">{event.source_count}</span>
          </div>
        )}
      </div>

      <div className="detail-section">
        <span className="detail-section__heading">Scores</span>
        <ScoreBar label="Severity" value={event.severity_score} />
        <ScoreBar label="Conf" value={event.confidence_score} />
      </div>

      {event.summary && (
        <div className="detail-section">
          <span className="detail-section__heading">Summary</span>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {event.summary}
          </p>
        </div>
      )}
    </div>
  )
}

function hotspotSummary(h) {
  const trend = h.trend_state === 'escalating' ? 'Escalating'
              : h.trend_state === 'declining'  ? 'Declining'
              : 'Ongoing'
  const sev   = h.severity_score >= 0.8 ? 'high-severity'
              : h.severity_score >= 0.5 ? 'moderate-severity'
              : 'low-severity'
  return `${trend} ${sev} cluster with ${h.event_count} event${h.event_count !== 1 ? 's' : ''}. Priority score ${Math.round(h.priority_score * 100)}.`
}

function HotspotDetail({ hotspot }) {
  return (
    <div className="detail-body">
      <div className="detail-title">{hotspot.name || 'Unnamed Hotspot'}</div>

      <div className="detail-meta">
        <div className="detail-row">
          <span className="detail-row__label">Status</span>
          <span className="detail-row__value detail-row__value--primary">{hotspot.status_label}</span>
        </div>
        <div className="detail-row">
          <span className="detail-row__label">Trend</span>
          <span className="detail-row__value">{hotspot.trend_state || '—'}</span>
        </div>
        <div className="detail-row">
          <span className="detail-row__label">Events</span>
          <span className="detail-row__value">{hotspot.event_count}</span>
        </div>
        {hotspot.last_computed_at && (
          <div className="detail-row">
            <span className="detail-row__label">Computed</span>
            <span className="detail-row__value">{formatDate(hotspot.last_computed_at)}</span>
          </div>
        )}
      </div>

      <div className="detail-section">
        <span className="detail-section__heading">Scores</span>
        <ScoreBar label="Priority" value={hotspot.priority_score} />
        <ScoreBar label="Severity" value={hotspot.severity_score} />
        <ScoreBar label="Momentum" value={hotspot.momentum_score} />
        <ScoreBar label="Conf" value={hotspot.confidence_score} />
      </div>

      <div className="detail-section">
        <span className="detail-section__heading">Centroid</span>
        <div className="detail-row">
          <span className="detail-row__label">Lat</span>
          <span className="detail-row__value">{hotspot.centroid_lat.toFixed(4)}</span>
        </div>
        <div className="detail-row">
          <span className="detail-row__label">Lon</span>
          <span className="detail-row__value">{hotspot.centroid_lon.toFixed(4)}</span>
        </div>
      </div>

      <div className="detail-section">
        <span className="detail-section__heading">Assessment</span>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          {hotspotSummary(hotspot)}
        </p>
      </div>
    </div>
  )
}

export default function DetailPane({ item, onClose }) {
  const paneRef = useRef(null)

  // Reset scroll to top whenever the selected item changes
  useEffect(() => {
    if (paneRef.current) paneRef.current.scrollTop = 0
  }, [item])

  if (!item) {
    return (
      <div className="detail-pane detail-pane--empty">
        <span className="detail-pane__hint">
          Select an event or priority to view details
        </span>
      </div>
    )
  }

  return (
    <div className="detail-pane" ref={paneRef}>
      <div className="detail-pane__header">
        <span className="detail-pane__type">{item.type}</span>
        <button className="detail-pane__close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {item.type === 'event'
        ? <EventDetail event={item.data} />
        : <HotspotDetail hotspot={item.data} />
      }
    </div>
  )
}
