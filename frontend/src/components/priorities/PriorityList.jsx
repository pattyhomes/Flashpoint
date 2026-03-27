function trendIcon(state) {
  if (state === 'escalating') return '↑'
  if (state === 'declining')  return '↓'
  return '→'
}

function Metric({ label, value }) {
  return (
    <span className="metric">
      <span className="metric__label">{label}</span>
      <span className="metric__value">{Math.round(value * 100)}</span>
    </span>
  )
}

function PriorityCard({ hotspot, rank, isSelected, onSelect }) {
  const trend = hotspot.trend_state || 'stable'
  return (
    <button
      className={`priority-card priority-card--${trend}${isSelected ? ' priority-card--selected' : ''}`}
      onClick={onSelect}
    >
      <span className="priority-card__rank">{rank}</span>
      <div className="priority-card__body">
        <div className="priority-card__name">{hotspot.name || 'Unnamed Hotspot'}</div>
        <div className="priority-card__label">{hotspot.status_label}</div>
        <div className="priority-card__metrics">
          <Metric label="SEV" value={hotspot.severity_score} />
          <Metric label="MOM" value={hotspot.momentum_score} />
          <Metric label="CONF" value={hotspot.confidence_score} />
        </div>
      </div>
      <span className={`priority-card__trend trend--${trend}`}>{trendIcon(trend)}</span>
    </button>
  )
}

export default function PriorityList({ priorities, selectedItem, onSelect }) {
  return (
    <div className="priority-list">
      <div className="panel-header">
        <span className="panel-header__title">Top Priorities</span>
        <span className="panel-header__count">{priorities.length}</span>
      </div>
      <div className="priority-list__items">
        {priorities.length === 0 && (
          <span className="priority-list__empty">No priorities match the current filters.</span>
        )}
        {priorities.map((p, i) => (
          <PriorityCard
            key={p.id}
            hotspot={p}
            rank={i + 1}
            isSelected={selectedItem?.type === 'hotspot' && selectedItem?.data?.id === p.id}
            onSelect={() => onSelect({ type: 'hotspot', data: p })}
          />
        ))}
      </div>
    </div>
  )
}
