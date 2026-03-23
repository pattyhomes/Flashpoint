import { useRef, useEffect } from 'react'

function severityColor(score) {
  if (score >= 0.8) return '#ef4444'
  if (score >= 0.6) return '#f59e0b'
  if (score >= 0.4) return '#eab308'
  return '#22c55e'
}

function relativeTime(iso) {
  if (!iso) return '—'
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  return `${Math.floor(min / 60)}h`
}

function EventRow({ event, isSelected, onSelect }) {
  const location = [event.city, event.state].filter(Boolean).join(', ')
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
      <span className="event-row__type">{event.event_type}</span>
      <span className="event-row__title">{event.title}</span>
      <span className="event-row__location">{location}</span>
      <span className="event-row__time">{relativeTime(event.occurred_at)}</span>
    </button>
  )
}

export default function EventFeed({ events, selectedItem, onSelect }) {
  const listRef = useRef(null)

  // Scroll selected row into view when selection changes externally (map/priorities)
  useEffect(() => {
    if (!selectedItem || selectedItem.type !== 'event' || !listRef.current) return
    const el = listRef.current.querySelector(`[data-id="${selectedItem.data.id}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [selectedItem])

  return (
    <div className="event-feed">
      <div className="panel-header">
        <span className="panel-header__title">Event Feed</span>
        <span className="panel-header__count">{events.length}</span>
      </div>
      <div className="event-feed__list" ref={listRef}>
        {events.map(event => (
          <EventRow
            key={event.id}
            event={event}
            isSelected={selectedItem?.type === 'event' && selectedItem?.data?.id === event.id}
            onSelect={() => onSelect({ type: 'event', data: event })}
          />
        ))}
      </div>
    </div>
  )
}
