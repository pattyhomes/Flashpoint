import { useEffect, useRef } from 'react'
import { formatDate, relativeTime } from '../../utils/time.js'

function pct(value) {
  return Math.round((value || 0) * 100)
}

function specificityLabel(value) {
  if (value === 'low_location') return 'LOW LOC'
  if (value === 'source_gap') return 'SRC GAP'
  if (value === 'classified') return 'CLASS'
  return value || 'SPEC'
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

function CitationRefs({ ids = [], citationsById }) {
  const refs = ids.map(id => citationsById.get(id)).filter(Boolean)
  if (refs.length === 0) return null
  return (
    <span className="briefing-cites">
      {refs.map(citation => (
        citation.url ? (
          <a key={citation.id} href={citation.url} target="_blank" rel="noreferrer">
            {citation.id}
          </a>
        ) : (
          <b key={citation.id}>{citation.id}</b>
        )
      ))}
    </span>
  )
}

function WhyNowSection({ whyNow, citationsById }) {
  if (!whyNow) return null
  const delta = whyNow.change_count > 0 ? `+${whyNow.change_count}` : String(whyNow.change_count)
  return (
    <div className="briefing-block">
      <div className="briefing-block__title">
        <span>Why Now</span>
        <b>{whyNow.current_24h_count} / 24H</b>
      </div>
      <p>{whyNow.summary}</p>
      <div className="briefing-window-strip">
        <span><b>NOW</b>{whyNow.current_24h_count}</span>
        <span><b>PRIOR</b>{whyNow.previous_24h_count}</span>
        <span><b>DELTA</b>{delta}</span>
        <span><b>MOM</b>{pct(whyNow.momentum_score)}</span>
      </div>
      <div className="briefing-drivers">
        {(whyNow.drivers || []).map(driver => (
          <div key={driver.label} className="briefing-driver">
            <span>{driver.label}</span>
            <b>{driver.value}</b>
            <em>{driver.detail}</em>
            <CitationRefs ids={driver.citation_ids} citationsById={citationsById} />
          </div>
        ))}
      </div>
    </div>
  )
}

function WhatHappenedSection({ whatHappened, citationsById }) {
  if (!whatHappened) return null
  return (
    <div className="briefing-block">
      <div className="briefing-block__title">
        <span>What Happened</span>
        <b>{(whatHappened.timeline_groups || []).length} WINDOWS</b>
      </div>
      <p>{whatHappened.summary}</p>
      <div className="briefing-type-strip">
        {(whatHappened.dominant_event_types || []).slice(0, 4).map(type => (
          <span key={type.label}><b>{type.label}</b>{type.value}</span>
        ))}
      </div>
      <div className="briefing-group-list">
        {(whatHappened.timeline_groups || []).map(group => (
          <div key={group.label} className="briefing-group">
            <div className="briefing-group__head">
              <span>{group.label}</span>
              <b>{group.event_count} EVT</b>
              <em>{group.dominant_event_type || 'activity'}</em>
              <CitationRefs ids={group.citation_ids} citationsById={citationsById} />
            </div>
            <p>{group.summary}</p>
            {(group.representative_events || []).slice(0, 2).map(event => (
              <div key={event.event_id} className="briefing-group-event">
                <span>{relativeTime(event.occurred_at)}</span>
                <b>{event.display_title || event.title}</b>
                {event.is_generic_classification && <em>{specificityLabel(event.specificity_level)}</em>}
                <CitationRefs ids={event.citation_ids} citationsById={citationsById} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function SourceReadSection({ sourceAssessment }) {
  if (!sourceAssessment) return null
  return (
    <div className="briefing-block briefing-block--source">
      <div className="briefing-block__title">
        <span>Source Read</span>
        <b>{sourceAssessment.citation_count_returned}/{sourceAssessment.citation_count_total} CITES</b>
      </div>
      <p>{sourceAssessment.summary}</p>
      <div className="briefing-source-strip">
        <span><b>COUNTED</b>{sourceAssessment.counted_source_count}</span>
        <span><b>PROV</b>{sourceAssessment.provenance_only_count}</span>
        <span><b>FAMILIES</b>{(sourceAssessment.counted_source_families || []).join(', ') || 'none'}</span>
      </div>
      <div className="briefing-source-notes">
        {(sourceAssessment.notes || []).map(note => <span key={note}>{note}</span>)}
      </div>
    </div>
  )
}

function HotspotBriefing({ briefing, loading }) {
  if (loading && !briefing) {
    return (
      <section className="detail-section briefing-panel">
        <div className="detail-section__title">
          <span>Briefing</span>
          <b>LOADING</b>
        </div>
        <span className="empty-note">Building grounded hotspot briefing.</span>
      </section>
    )
  }
  if (!briefing) return null

  const citationsById = new Map((briefing.citations || []).map(citation => [citation.id, citation]))
  return (
    <section className="detail-section briefing-panel">
      <div className="detail-section__title">
        <span>Briefing</span>
        {loading && <b>REFRESHING</b>}
      </div>
      <div className="briefing-panel__summary">
        <b>{briefing.headline}</b>
        <p>{briefing.why_it_matters}</p>
      </div>
      {briefing.specificity_assessment?.low_specificity && (
        <div className="briefing-specificity-warning">
          <b>LOW SPECIFICITY</b>
          <span>{briefing.specificity_assessment.summary}</span>
        </div>
      )}
      <WhyNowSection whyNow={briefing.why_now} citationsById={citationsById} />
      <WhatHappenedSection whatHappened={briefing.what_happened} citationsById={citationsById} />
      <SourceReadSection sourceAssessment={briefing.source_assessment} />
      {(briefing.citations || []).length > 0 && (
        <div className="briefing-citation-ledger">
          {briefing.citations.slice(0, 6).map(citation => (
            <div key={citation.id} className="briefing-citation-row">
              <span>{citation.id}</span>
              <b>{citation.counted ? 'COUNTED' : 'PROV'}</b>
              {citation.url ? (
                <a href={citation.url} target="_blank" rel="noreferrer">
                  {citation.source_name || citation.source_type}
                </a>
              ) : (
                <em>{citation.source_name || citation.source_type}</em>
              )}
              <i>{citation.note}</i>
            </div>
          ))}
        </div>
      )}
      {(briefing.caveats || []).length > 0 && (
        <div className="briefing-caveats">
          {briefing.caveats.map(caveat => <span key={caveat}>{caveat}</span>)}
        </div>
      )}
    </section>
  )
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
  const displayTitle = enriched.display_title || event.display_title || event.title
  const specificityReason = enriched.specificity_reason || event.specificity_reason
  const specificityLevel = enriched.specificity_level || event.specificity_level
  return (
    <div className="detail-body">
      <div className="detail-kicker">EVENT · {event.source_name}</div>
      <h2>{displayTitle}</h2>
      <div className="detail-meta-grid">
        <span><b>ID</b>{event.id}</span>
        <span><b>TYPE</b>{event.event_type}</span>
        <span><b>WHERE</b>{location}</span>
        <span><b>WHEN</b>{formatDate(event.occurred_at)}</span>
      </div>
      {specificityReason && (
        <div className={`specificity-note specificity-note--${specificityLevel || 'specific'}`}>
          <b>{specificityLabel(specificityLevel)}</b>
          <span>{specificityReason}</span>
        </div>
      )}
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

function HotspotDetail({ hotspot, memberEvents = [], loading, briefing, briefingLoading, trend, signals }) {
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
      <HotspotBriefing briefing={briefing} loading={briefingLoading} />
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
            <span>{event.is_generic_classification ? 'CLASS' : specificityLabel(event.specificity_level) || event.event_type}</span>
            <b>{event.display_title || event.title}</b>
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
  hotspotBriefing,
  hotspotBriefingLoading,
  hotspotTrend,
  eventDetail,
  eventDetailLoading,
  signals = [],
}) {
  const paneRef = useRef(null)

  useEffect(() => {
    const body = paneRef.current?.querySelector('.detail-body')
    if (body) body.scrollTop = 0
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
        <button type="button" onClick={onClose} aria-label="Return to the rail">BACK</button>
        <span>{item.type === 'hotspot' ? 'HOTSPOT DETAIL' : 'EVENT DETAIL'}</span>
        <button type="button" onClick={onClose} aria-label="Collapse the detail rail">COLLAPSE</button>
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
          briefing={hotspotBriefing}
          briefingLoading={hotspotBriefingLoading}
          trend={hotspotTrend}
          signals={signals}
        />
      )}
      <div className="detail-pane__footer">
        <button type="button" onClick={onClose}>COLLAPSE DETAIL</button>
      </div>
    </div>
  )
}
