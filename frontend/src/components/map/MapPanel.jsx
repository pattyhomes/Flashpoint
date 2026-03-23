// Placeholder — ready for map library drop-in (Leaflet / MapLibre).
// Props contract is established; parent passes data when map is wired.
export default function MapPanel({ events = [], hotspots = [] }) {
  return (
    <div className="map-panel">
      <span className="map-panel__label">Operational Map</span>
      <div className="map-panel__stats">
        <div className="map-panel__stat">
          <span className="map-panel__stat-value">{events.length}</span>
          <span className="map-panel__stat-label">Events</span>
        </div>
        <div className="map-panel__stat">
          <span className="map-panel__stat-value">{hotspots.length}</span>
          <span className="map-panel__stat-label">Hotspots</span>
        </div>
      </div>
    </div>
  )
}
