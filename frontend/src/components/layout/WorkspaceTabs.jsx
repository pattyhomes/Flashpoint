export default function WorkspaceTabs({ activeWorkspace, onSetWorkspace, counts }) {
  const tabs = [
    { key: 'map', label: 'Live Map', count: counts.events },
    { key: 'incidents', label: 'Incidents', count: counts.visibleEvents },
  ]

  return (
    <div className="workspace-tabs" role="tablist" aria-label="Workspaces">
      {tabs.map(tab => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={activeWorkspace === tab.key}
          className={activeWorkspace === tab.key ? 'is-active' : ''}
          onClick={() => onSetWorkspace(tab.key)}
        >
          <span>{tab.label}</span>
          <span className="tab-count">{tab.count ?? 0}</span>
        </button>
      ))}
      <div className="workspace-tabs__spacer" />
      <span className="workspace-tabs__note">
        {counts.signals ?? 0} SIGNALS · {counts.hotspots ?? 0} HOTSPOTS
      </span>
    </div>
  )
}
