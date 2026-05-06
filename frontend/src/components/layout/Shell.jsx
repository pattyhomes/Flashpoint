import MapOverlay from './MapOverlay.jsx'

export default function Shell({ left, map, right, bottom, status }) {
  return (
    <div className="shell">
      <MapOverlay as="aside" className="shell__left">{left}</MapOverlay>
      <main className="shell__map">{map}</main>
      <MapOverlay as="aside" className="shell__right">{right}</MapOverlay>
      <MapOverlay as="section" className="shell__bottom">{bottom}</MapOverlay>
      <MapOverlay as="footer" className="shell__status">{status}</MapOverlay>
    </div>
  )
}
