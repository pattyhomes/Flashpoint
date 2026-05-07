function pct(value) {
  return Math.round((value || 0) * 100)
}

function trendLabel(state) {
  if (state === 'escalating') return 'UP'
  if (state === 'declining') return 'DOWN'
  return 'STABLE'
}

function MiniBars({ hotspot }) {
  const base = pct(hotspot.priority_score)
  const mom = pct(hotspot.momentum_score)
  const sev = pct(hotspot.severity_score)
  const conf = pct(hotspot.confidence_score)
  const values = [conf * 0.5, sev * 0.72, base * 0.86, Math.max(mom, 24), base]
  return (
    <span className="mini-bars" aria-hidden="true">
      {values.map((value, index) => (
        <i key={index} style={{ height: `${Math.max(14, Math.min(38, value * 0.38))}px` }} />
      ))}
    </span>
  )
}

function PriorityCard({ hotspot, rank, isSelected, onSelect }) {
  const trend = hotspot.trend_state || 'stable'
  return (
    <button
      className={`v3-priority-card v3-priority-card--${trend}${isSelected ? ' is-selected' : ''}`}
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
      <MiniBars hotspot={hotspot} />
      <span className={`v3-priority-card__trend trend--${trend}`}>{trendLabel(trend)}</span>
    </button>
  )
}

export default function PriorityList({ priorities, selectedItem, onSelect }) {
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
            rank={index + 1}
            isSelected={selectedItem?.type === 'hotspot' && selectedItem?.data?.id === priority.id}
            onSelect={() => onSelect({ type: 'hotspot', data: priority })}
          />
        ))}
      </div>
    </div>
  )
}
