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

export default function FilterRail({ activeTypes, onToggle, onClear, layersVisible, onToggleLayer }) {
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
    </div>
  )
}
