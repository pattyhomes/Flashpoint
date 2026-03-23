const EVENT_TYPES = [
  { key: 'violence',   label: 'Violence',   color: '#ef4444' },
  { key: 'unrest',     label: 'Unrest',     color: '#f59e0b' },
  { key: 'disruption', label: 'Disruption', color: '#eab308' },
  { key: 'protest',    label: 'Protest',    color: '#22c55e' },
]

export default function FilterRail({ activeTypes, onToggle, onClear }) {
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
        <p className="filter-section__placeholder">Map layers coming soon</p>
      </div>
    </div>
  )
}
