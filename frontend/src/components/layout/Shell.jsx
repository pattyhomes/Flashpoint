import MapOverlay from './MapOverlay.jsx'

export default function Shell({ top, tabs, nav, map, right, drawer, status, rightExpanded = false }) {
  return (
    <div className="workstation">
      <MapOverlay as="header" className="workstation__top">{top}</MapOverlay>
      <MapOverlay as="nav" className="workstation__tabs">{tabs}</MapOverlay>
      <MapOverlay as="aside" className="workstation__nav">{nav}</MapOverlay>
      <main className="workstation__map">{map}</main>
      <MapOverlay
        as="aside"
        className={`workstation__right${rightExpanded ? ' workstation__right--expanded' : ''}`}
      >
        {right}
      </MapOverlay>
      {drawer && <MapOverlay as="section" className="workstation__drawer">{drawer}</MapOverlay>}
      <MapOverlay as="footer" className="workstation__telemetry">{status}</MapOverlay>
    </div>
  )
}
