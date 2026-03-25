const EVENT_TYPES = [
  { key: 'violence',   label: 'Violence',   color: '#ef4444' },
  { key: 'unrest',     label: 'Unrest',     color: '#f59e0b' },
  { key: 'disruption', label: 'Disruption', color: '#eab308' },
  { key: 'protest',    label: 'Protest',    color: '#22c55e' },
]

const LAYERS = [
  { key: 'events',   label: 'Events',   color: '#4a9eff' },
  { key: 'hotspots', label: 'Hotspots', color: '#9aa0b0' },
  { key: 'heatmap',  label: 'Heatmap',  color: '#f59e0b' },
]

const SEV_LEVELS = [
  { label: 'Any',  value: 0.0 },
  { label: 'Low',  value: 0.4 },
  { label: 'Med',  value: 0.6 },
  { label: 'High', value: 0.8 },
]

const CONF_LEVELS = [
  { label: 'Any',  value: 0.0 },
  { label: 'Med',  value: 0.5 },
  { label: 'High', value: 0.75 },
]

const TREND_STATES = [
  { key: 'escalating', label: 'Escalating', color: '#ef4444' },
  { key: 'stable',     label: 'Stable',     color: '#9aa0b0' },
  { key: 'declining',  label: 'Declining',  color: '#22c55e' },
]

export default function FilterRail({
  activeTypes, onToggle, onClear,
  layersVisible, onToggleLayer,
  minSeverity, onSetSeverity,
  minConfidence, onSetConfidence,
  activeTrends, onToggleTrend,
  eventTypeCounts = {},
}) {
  const allActive = activeTypes.size === 0

  return (
    <div className="filter-rail">
      <div>
        <p className="filter-section__heading">Event Types</p>
        <div className="filter-section__chips">
          <button
            className={`filter-chip${allActive ? ' filter-chip--active' : ''}`}
            onClick={onClear}
          >
            All
          </button>
          {EVENT_TYPES.map(t => (
            <button
              key={t.key}
              className={`filter-chip${activeTypes.has(t.key) ? ' filter-chip--active' : ''}`}
              onClick={() => onToggle(t.key)}
            >
              <span className="filter-chip__dot" style={{ backgroundColor: t.color }} />
              {t.label}
              <span className="filter-chip__count">{eventTypeCounts[t.key] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="filter-section__heading">Layers</p>
        <div className="filter-section__chips">
          {LAYERS.map(l => (
            <button
              key={l.key}
              className={`filter-chip${layersVisible[l.key] ? ' filter-chip--active' : ''}`}
              onClick={() => onToggleLayer(l.key)}
            >
              <span className="filter-chip__dot" style={{ backgroundColor: l.color }} />
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="filter-section__heading">Min Severity</p>
        <div className="filter-section__chips filter-section__chips--row">
          {SEV_LEVELS.map(l => (
            <button
              key={l.value}
              className={`filter-chip${minSeverity === l.value ? ' filter-chip--active' : ''}`}
              onClick={() => onSetSeverity(l.value)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="filter-section__heading">Min Confidence</p>
        <div className="filter-section__chips filter-section__chips--row">
          {CONF_LEVELS.map(l => (
            <button
              key={l.value}
              className={`filter-chip${minConfidence === l.value ? ' filter-chip--active' : ''}`}
              onClick={() => onSetConfidence(l.value)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="filter-section__heading">Trend</p>
        <div className="filter-section__chips">
          {TREND_STATES.map(t => (
            <button
              key={t.key}
              className={`filter-chip${activeTrends.has(t.key) ? ' filter-chip--active' : ''}`}
              onClick={() => onToggleTrend(t.key)}
            >
              <span className="filter-chip__dot" style={{ backgroundColor: t.color }} />
              {t.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
