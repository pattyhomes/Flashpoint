import EventFeed from '../feed/EventFeed.jsx'
import { relativeTime } from '../../utils/time.js'

function distanceMiles(aLat, aLon, bLat, bLon) {
  const radius = 3958.8
  const toRad = (value) => value * Math.PI / 180
  const dLat = toRad(bLat - aLat)
  const dLon = toRad(bLon - aLon)
  const lat1 = toRad(aLat)
  const lat2 = toRad(bLat)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * radius * Math.asin(Math.sqrt(h))
}

function filteredSignals(signals, focus) {
  if (!focus) return signals.slice(0, 20)
  return signals
    .map(signal => ({ signal, distance: distanceMiles(focus.lat, focus.lon, signal.latitude, signal.longitude) }))
    .filter(item => item.distance <= 80)
    .sort((a, b) => a.distance - b.distance)
    .map(item => item.signal)
}

export default function IncidentsDrawer({
  open,
  onClose,
  events,
  loadedCount,
  total,
  hasMore,
  onLoadMore,
  loadingMore,
  selectedItem,
  onSelect,
  signals,
  signalFocus,
}) {
  if (!open) return null
  const scopedSignals = filteredSignals(signals, signalFocus)

  return (
    <div className="incidents-drawer">
      <div className="incidents-drawer__head">
        <div>
          <span>INCIDENTS</span>
          <b>{signalFocus ? 'SIGNAL AREA' : 'EVENT STREAM'}</b>
        </div>
        <button type="button" onClick={onClose}>CLOSE</button>
      </div>
      <div className="incidents-drawer__body">
        <EventFeed
          events={events}
          loadedCount={loadedCount}
          total={total}
          hasMore={hasMore}
          onLoadMore={onLoadMore}
          loadingMore={loadingMore}
          selectedItem={selectedItem}
          onSelect={onSelect}
        />
        <section className="signal-drawer-list">
          <div className="rail-section-title">
            <span>Eligible Signals</span>
            <b>{scopedSignals.length}</b>
          </div>
          {scopedSignals.length === 0 ? (
            <span className="empty-note">No eligible signal leads in this area.</span>
          ) : scopedSignals.map(signal => (
            <article key={signal.id} className="drawer-signal-row">
              <div>
                <span>{signal.source_family}</span>
                <b>CONF {Math.round(signal.confidence_score * 100)}</b>
                <i>{relativeTime(signal.observed_at)}</i>
              </div>
              <p>{signal.title}</p>
            </article>
          ))}
        </section>
      </div>
    </div>
  )
}
