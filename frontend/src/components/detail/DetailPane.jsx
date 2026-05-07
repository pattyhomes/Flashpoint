import { useEffect, useRef } from 'react'
import { formatDate, relativeTime } from '../../utils/time.js'

function pct(value) {
  return Math.round((value || 0) * 100)
}

function severityColor(score) {
  if (score >= 0.8) return '#ff3a2e'
  if (score >= 0.6) return '#ff7a18'
  if (score >= 0.4) return '#ffb524'
  return '#5d8aa8'
}

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

function nearbySignals(signals, lat, lon) {
  if (!lat || !lon) return []
  return signals
    .map(signal => ({ signal, distance: distanceMiles(lat, lon, signal.latitude, signal.longitude) }))
    .filter(item => item.distance <= 60)
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 5)
}

function ScoreGrid({ scores }) {
  return (
    <div className="score-grid">
      {scores.map(score => (
        <div key={score.label} className="score-box">
          <span>{score.label}</span>
          <b>{pct(score.value)}</b>
          <i style={{ width: `${pct(score.value)}%`, background: severityColor(score.value) }} />
        </div>
      ))}
    </div>
  )
}

function TrendChart({ trend }) {
  const buckets = trend?.buckets || []
  const max = Math.max(1, ...buckets.map(bucket => bucket.event_count || 0))
  return (
    <div className="trend-chart" aria-label="24 hour event volume">
      <div className="trend-chart__head">
        <span>24H EVENT VOLUME</span>
        <b>{buckets.reduce((sum, bucket) => sum + (bucket.event_count || 0), 0)} EVT</b>
      </div>
      <div className="trend-chart__bars">
        {buckets.map(bucket => (
          <i
            key={bucket.bucket_start}
            title={`${bucket.event_count} events`}
            style={{
              height: `${Math.max(4, (bucket.event_count / max) * 54)}px`,
              background: bucket.event_count > 0 ? severityColor(bucket.max_severity) : 'rgba(255,255,255,0.08)',
            }}
          />
        ))}
      </div>
    </div>
  )
}

function Sources({ sources }) {
  if (!sources || sources.length === 0) return <span className="empty-note">No source ledger attached.</span>
  return sources.map(source => (
    <div key={source.id} className="source-ledger-row">
      <span>{source.source_name || source.source_type}</span>
      <b>{source.source_trust_weight === 0 ? 'COPY' : 'INDEP'}</b>
      <a href={source.source_url || undefined} target="_blank" rel="noreferrer">
        {source.source_title || source.source_url || 'Source record'}
      </a>
      <i>{relativeTime(source.source_published_at)}</i>
    </div>
  ))
}

function SignalContext({ signals, lat, lon }) {
  const rows = nearbySignals(signals, lat, lon)
  return (
    <section className="detail-section">
      <div className="detail-section__title">
        <span>Nearby Signals</span>
        <b>CONTEXT ONLY</b>
      </div>
      {rows.length === 0 ? (
        <span className="empty-note">No eligible signal context nearby.</span>
      ) : rows.map(({ signal, distance }) => (
        <div key={signal.id} className="signal-context-row">
          <span>{signal.source_family}</span>
          <b>{Math.round(distance)} mi</b>
          <em>{signal.title}</em>
        </div>
      ))}
    </section>
  )
}

function EventDetail({ event, detail, detailLoading, signals }) {
  const enriched = detail || event
  const location = [event.city, event.state].filter(Boolean).join(', ') || event.country
  return (
    <div className="detail-body">
      <div className="detail-kicker">EVENT · {event.source_name}</div>
      <h2>{event.source_name === 'gdelt' ? `${event.event_type} signal — ${location}` : event.title}</h2>
      <div className="detail-meta-grid">
        <span><b>ID</b>{event.id}</span>
        <span><b>TYPE</b>{event.event_type}</span>
        <span><b>WHERE</b>{location}</span>
        <span><b>WHEN</b>{formatDate(event.occurred_at)}</span>
      </div>
      <ScoreGrid scores={[
        { label: 'Severity', value: event.severity_score },
        { label: 'Confidence', value: event.confidence_score },
      ]} />
      {event.summary && (
        <section className="detail-section">
          <div className="detail-section__title"><span>Summary</span></div>
          <p>{event.summary}</p>
        </section>
      )}
      <SignalContext signals={signals} lat={event.latitude} lon={event.longitude} />
      <section className="detail-section">
        <div className="detail-section__title">
          <span>Sources</span>
          {detailLoading && <b>LOADING</b>}
        </div>
        <Sources sources={enriched.sources || []} />
      </section>
    </div>
  )
}

function HotspotDetail({ hotspot, memberEvents = [], loading, trend, signals }) {
  return (
    <div className="detail-body">
      <div className="detail-kicker">PRIORITY HOTSPOT · {hotspot.trend_state || 'stable'}</div>
      <h2>{hotspot.name || 'Unnamed Hotspot'}</h2>
      <div className="detail-meta-grid">
        <span><b>STATUS</b>{hotspot.status_label || 'Active'}</span>
        <span><b>EVENTS</b>{hotspot.event_count}</span>
        <span><b>LAT</b>{hotspot.centroid_lat.toFixed(3)}</span>
        <span><b>LON</b>{hotspot.centroid_lon.toFixed(3)}</span>
      </div>
      <ScoreGrid scores={[
        { label: 'Priority', value: hotspot.priority_score },
        { label: 'Severity', value: hotspot.severity_score },
        { label: 'Momentum', value: hotspot.momentum_score },
        { label: 'Confidence', value: hotspot.confidence_score },
      ]} />
      <TrendChart trend={trend} />
      <SignalContext signals={signals} lat={hotspot.centroid_lat} lon={hotspot.centroid_lon} />
      <section className="detail-section">
        <div className="detail-section__title">
          <span>Member Events</span>
          {loading && <b>LOADING</b>}
        </div>
        {memberEvents.length === 0 ? (
          <span className="empty-note">No events assigned.</span>
        ) : memberEvents.slice(0, 10).map(event => (
          <div key={event.id} className="member-event-row">
            <i style={{ background: severityColor(event.severity_score) }} />
            <span>{event.event_type}</span>
            <b>{event.source_name === 'gdelt' ? `${event.event_type} signal — ${event.city || event.country}` : event.title}</b>
            <em>{relativeTime(event.occurred_at)}</em>
          </div>
        ))}
      </section>
    </div>
  )
}

export default function DetailPane({
  item,
  onClose,
  hotspotDetail,
  hotspotDetailLoading,
  hotspotTrend,
  eventDetail,
  eventDetailLoading,
  signals = [],
}) {
  const paneRef = useRef(null)

  useEffect(() => {
    if (paneRef.current) paneRef.current.scrollTop = 0
  }, [item])

  if (!item) {
    return (
      <div className="detail-pane detail-pane--empty">
        <span className="empty-note">Select an event or priority for detail.</span>
      </div>
    )
  }

  return (
    <div className="detail-pane" ref={paneRef}>
      <div className="detail-pane__header">
        <button type="button" onClick={onClose}>BACK</button>
        <span>{item.type === 'hotspot' ? 'HOTSPOT DETAIL' : 'EVENT DETAIL'}</span>
      </div>
      {item.type === 'event' ? (
        <EventDetail
          event={item.data}
          detail={eventDetail}
          detailLoading={eventDetailLoading}
          signals={signals}
        />
      ) : (
        <HotspotDetail
          hotspot={hotspotDetail || item.data}
          memberEvents={hotspotDetail?.member_events || []}
          loading={hotspotDetailLoading}
          trend={hotspotTrend}
          signals={signals}
        />
      )}
    </div>
  )
}
