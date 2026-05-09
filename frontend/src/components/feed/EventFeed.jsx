import { useRef, useEffect } from 'react'
import { relativeTime } from '../../utils/time'

function severityColor(score) {
  if (score >= 0.8) return '#ef4444'
  if (score >= 0.6) return '#f59e0b'
  if (score >= 0.4) return '#eab308'
  return '#22c55e'
}

function specificityLabel(value) {
  if (value === 'low_location') return 'LOW LOC'
  if (value === 'source_gap') return 'SRC GAP'
  if (value === 'classified') return 'CLASS'
  return value || 'SPEC'
}

function qualityLabel(value) {
  if (value === 'article_backed_classification') return 'ARTICLE'
  if (value === 'corroborated_classification') return 'CORROB'
  if (value === 'detector_only') return 'DETECT'
  if (value === 'broad_detector') return 'BROAD'
  if (value === 'incident_specific') return 'INCIDENT'
  return null
}

function EventRow({ event, isSelected, onSelect }) {
  const location = [event.city, event.state].filter(Boolean).join(', ')
  const displayTitle = event.display_title || event.title
  const specificity = qualityLabel(event.quality_tier) || (event.is_generic_classification ? 'CLASS' : specificityLabel(event.specificity_level))
  return (
    <button
      data-id={event.id}
      className={`event-row${isSelected ? ' event-row--selected' : ''}`}
      onClick={onSelect}
    >
      <span
        className="event-row__dot"
        style={{ backgroundColor: severityColor(event.severity_score) }}
      />
      <span className="event-row__type">{specificity || event.event_type}</span>
      <span className="event-row__title">{displayTitle}</span>
      <span className="event-row__location">{location}</span>
      <span className="event-row__time">{relativeTime(event.occurred_at)}</span>
    </button>
  )
}

export default function EventFeed({ events, loadedCount = 0, total = 0, hasMore = false, onLoadMore, loadingMore = false, selectedItem, onSelect }) {
  const listRef = useRef(null)

  // Scroll selected row into view when selection changes externally (map/priorities)
  useEffect(() => {
    if (!selectedItem || selectedItem.type !== 'event' || !listRef.current) return
    const el = listRef.current.querySelector(`[data-id="${selectedItem.data.id}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [selectedItem])

  // Primary count: loadedCount / total (both from backend universe)
  // Secondary: filtered visible count when filters reduce the visible set
  const primaryCount = hasMore ? `${loadedCount} / ${total}` : `${total}`
  const visibleLabel = events.length < loadedCount ? ` · ${events.length} visible` : ''

  return (
    <div className="event-feed">
      <div className="panel-header">
        <span className="panel-header__title">Event Feed</span>
        <span className="panel-header__count">{primaryCount}{visibleLabel}</span>
      </div>
      <div className="event-feed__list" ref={listRef}>
        {events.length === 0 && (
          <span className="event-feed__empty">No events match the current filters.</span>
        )}
        {[...events].sort((a, b) => {
          const eligibleDelta = Number(Boolean(b.eligible_for_hotspots)) - Number(Boolean(a.eligible_for_hotspots))
          if (eligibleDelta) return eligibleDelta
          return new Date(b.occurred_at) - new Date(a.occurred_at)
        }).map(event => (
          <EventRow
            key={event.id}
            event={event}
            isSelected={selectedItem?.type === 'event' && selectedItem?.data?.id === event.id}
            onSelect={() => onSelect({ type: 'event', data: event })}
          />
        ))}
        {hasMore && (
          <button
            className="event-feed__load-more"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : `Load more · ${total - loadedCount} remaining`}
          </button>
        )}
      </div>
    </div>
  )
}
