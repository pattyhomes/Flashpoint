function pct(value) {
  return Math.round((value || 0) * 100)
}

function trendLabel(state) {
  if (state === 'escalating') return 'UP'
  if (state === 'declining') return 'DOWN'
  return 'STABLE'
}

function ScoreBar({ label, value }) {
  const width = Math.max(2, Math.min(100, pct(value)))
  return (
    <span className={`priority-score-bar priority-score-bar--${label.toLowerCase()}`}>
      <span>{label}</span>
      <i>
        <b style={{ width: `${width}%` }} />
      </i>
    </span>
  )
}

function PriorityScoreBars({ hotspot }) {
  return (
    <span className="priority-score-bars" aria-label="Priority score breakdown">
      <ScoreBar label="PRI" value={hotspot.priority_score} />
      <ScoreBar label="SEV" value={hotspot.severity_score} />
      <ScoreBar label="MOM" value={hotspot.momentum_score} />
      <ScoreBar label="CONF" value={hotspot.confidence_score} />
    </span>
  )
}

function TimelineBars({ trend }) {
  const buckets = trend?.buckets || Array.from({ length: 24 }, (_, index) => ({
    bucket_start: `placeholder-${index}`,
    event_count: 0,
  }))
  const max = Math.max(1, ...buckets.map(bucket => bucket.event_count || 0))
  const total = buckets.reduce((sum, bucket) => sum + (bucket.event_count || 0), 0)
  return (
    <span
      className="priority-timeline"
      aria-label={`24 hour event timeline: ${total} events`}
      title={`${total} events in the last 24 hours`}
    >
      <span className="priority-timeline__head">
        <b>24H</b>
        <i>{total} EVT</i>
      </span>
      <span className="priority-timeline__bars">
        {buckets.map(bucket => (
          <i
            key={bucket.bucket_start}
            className={bucket.event_count > 0 ? 'has-events' : ''}
            style={{ height: `${Math.max(3, ((bucket.event_count || 0) / max) * 18)}px` }}
          />
        ))}
      </span>
    </span>
  )
}

function PriorityCard({ hotspot, timeline, rank, isSelected, onSelect }) {
  const trendState = hotspot.trend_state || 'stable'
  return (
    <button
      className={`v3-priority-card v3-priority-card--${trendState}${isSelected ? ' is-selected' : ''}`}
      onClick={onSelect}
      type="button"
    >
      <span className="v3-priority-card__stripe" />
      <span className="v3-priority-card__rank">{String(rank).padStart(2, '0')}</span>
      <span className="v3-priority-card__body">
        <span className="v3-priority-card__name">{hotspot.name || 'Unnamed Hotspot'}</span>
        <span className="v3-priority-card__meta">
          {hotspot.status_label || 'Active'} · {hotspot.event_count} EVT · PRI {pct(hotspot.priority_score)}
        </span>
        <span className="v3-priority-card__metrics">
          <b>SEV {pct(hotspot.severity_score)}</b>
          <b>MOM {pct(hotspot.momentum_score)}</b>
          <b>CONF {pct(hotspot.confidence_score)}</b>
        </span>
      </span>
      <PriorityScoreBars hotspot={hotspot} />
      <span className={`v3-priority-card__trend trend--${trendState}`}>{trendLabel(trendState)}</span>
      <TimelineBars trend={timeline} />
    </button>
  )
}

export default function PriorityList({ priorities, priorityTrends = {}, selectedItem, onSelect }) {
  return (
    <div className="v3-priority-list">
      <div className="rail-section-title">
        <span>Priorities</span>
        <b>{priorities.length}</b>
      </div>
      <div className="v3-priority-list__items">
        {priorities.length === 0 && (
          <span className="empty-note">No priorities match the current filters.</span>
        )}
        {priorities.map((priority, index) => (
          <PriorityCard
            key={priority.id}
            hotspot={priority}
            timeline={priorityTrends[priority.id]}
            rank={index + 1}
            isSelected={selectedItem?.type === 'hotspot' && selectedItem?.data?.id === priority.id}
            onSelect={() => onSelect({ type: 'hotspot', data: priority })}
          />
        ))}
      </div>
    </div>
  )
}
