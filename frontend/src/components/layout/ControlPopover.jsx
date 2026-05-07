const EVENT_TYPES = [
  { key: 'violence', label: 'Violence', color: '#ff3a2e' },
  { key: 'unrest', label: 'Unrest', color: '#ff7a18' },
  { key: 'disruption', label: 'Disruption', color: '#ffb524' },
  { key: 'protest', label: 'Protest', color: '#5d8aa8' },
]

const SEV_LEVELS = [
  { label: 'Any', value: 0.0 },
  { label: 'Low', value: 0.4 },
  { label: 'Med', value: 0.6 },
  { label: 'High', value: 0.8 },
]

const CONF_LEVELS = [
  { label: 'Any', value: 0.0 },
  { label: 'Med', value: 0.5 },
  { label: 'High', value: 0.75 },
]

const TRENDS = [
  { key: 'escalating', label: 'Escalating', color: '#ff5a3a' },
  { key: 'stable', label: 'Stable', color: '#aab2c0' },
  { key: 'declining', label: 'Declining', color: '#4ea36a' },
]

const LAYERS = [
  { key: 'confirmedHeat', label: 'Confirmed Heat', color: '#ff3a2e' },
  { key: 'signalHeat', label: 'Signal Heat', color: '#ffb524' },
  { key: 'events', label: 'Event Dots', color: '#e8ecf2' },
  { key: 'hotspots', label: 'Hotspots', color: '#ff7a18' },
]

function Chip({ active, children, color, ...props }) {
  return (
    <button type="button" className={`control-chip${active ? ' is-active' : ''}`} {...props}>
      {color && <span className="control-chip__dot" style={{ backgroundColor: color }} />}
      {children}
    </button>
  )
}

export default function ControlPopover({
  kind,
  activeTypes,
  onToggleType,
  onClearTypes,
  minSeverity,
  onSetSeverity,
  minConfidence,
  onSetConfidence,
  activeTrends,
  onToggleTrend,
  layersVisible,
  onToggleLayer,
  eventTypeCounts,
}) {
  if (!kind) return null

  if (kind === 'layers') {
    return (
      <div className="control-popover control-popover--layers">
        <span className="control-popover__title">Map Layers</span>
        <div className="control-popover__grid">
          {LAYERS.map(layer => (
            <Chip
              key={layer.key}
              color={layer.color}
              active={layersVisible[layer.key]}
              onClick={() => onToggleLayer(layer.key)}
            >
              {layer.label}
            </Chip>
          ))}
        </div>
      </div>
    )
  }

  const allActive = activeTypes.size === 0
  return (
    <div className="control-popover control-popover--filters">
      <span className="control-popover__title">Filters</span>
      <section>
        <span className="control-popover__label">Event Type</span>
        <div className="control-popover__grid">
          <Chip active={allActive} onClick={onClearTypes}>All</Chip>
          {EVENT_TYPES.map(type => (
            <Chip
              key={type.key}
              color={type.color}
              active={activeTypes.has(type.key)}
              onClick={() => onToggleType(type.key)}
            >
              {type.label}
              <span className="control-chip__count">{eventTypeCounts[type.key] ?? 0}</span>
            </Chip>
          ))}
        </div>
      </section>
      <section>
        <span className="control-popover__label">Severity</span>
        <div className="control-popover__row">
          {SEV_LEVELS.map(level => (
            <Chip key={level.value} active={minSeverity === level.value} onClick={() => onSetSeverity(level.value)}>
              {level.label}
            </Chip>
          ))}
        </div>
      </section>
      <section>
        <span className="control-popover__label">Confidence</span>
        <div className="control-popover__row">
          {CONF_LEVELS.map(level => (
            <Chip key={level.value} active={minConfidence === level.value} onClick={() => onSetConfidence(level.value)}>
              {level.label}
            </Chip>
          ))}
        </div>
      </section>
      <section>
        <span className="control-popover__label">Trend</span>
        <div className="control-popover__grid">
          {TRENDS.map(trend => (
            <Chip
              key={trend.key}
              color={trend.color}
              active={activeTrends.has(trend.key)}
              onClick={() => onToggleTrend(trend.key)}
            >
              {trend.label}
            </Chip>
          ))}
        </div>
      </section>
    </div>
  )
}
