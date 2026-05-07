const NAV_ITEMS = [
  { key: 'map', label: 'MAP' },
  { key: 'incidents', label: 'INC' },
  { key: 'sources', label: 'SRC' },
]

export default function NavRail({ activeWorkspace, onSetWorkspace, onShowSources, counts }) {
  return (
    <div className="nav-rail" aria-label="Primary navigation">
      <div className="nav-rail__stack">
        {NAV_ITEMS.map(item => {
          const active = item.key === 'sources' ? false : activeWorkspace === item.key
          const onClick = item.key === 'sources' ? onShowSources : () => onSetWorkspace(item.key)
          return (
            <button
              key={item.key}
              type="button"
              className={active ? 'is-active' : ''}
              onClick={onClick}
              aria-label={item.key === 'incidents' ? 'Open incidents drawer' : item.key === 'sources' ? 'Open sources rail' : 'Open map'}
            >
              <span>{item.label}</span>
              {item.key === 'incidents' && counts.leads > 0 && <i>{counts.leads}</i>}
            </button>
          )
        })}
      </div>
      <div className="nav-rail__status">
        <span />
      </div>
    </div>
  )
}
