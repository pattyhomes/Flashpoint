import { useState } from 'react'
import { relativeTime } from '../../utils/time'

function pct(value) {
  return Math.round((value || 0) * 100)
}

function ObservationRow({ observation, busy, onPromote, onDismiss, onLink }) {
  const [eventId, setEventId] = useState('')
  const evidence = observation.evidence
  const canPromote = Boolean(
    observation.latitude &&
    observation.longitude &&
    observation.observed_at &&
    observation.candidate_event_type
  )
  return (
    <div className="observation-row">
      <div className="observation-row__main">
        <div className="observation-row__meta">
          <span className={`observation-row__tier observation-row__tier--${evidence?.trust_tier || 'weak'}`}>
            {evidence?.trust_tier || 'weak'}
          </span>
          <span>{evidence?.source_type || 'source'}</span>
          <span>{relativeTime(observation.observed_at || evidence?.published_at)}</span>
        </div>
        <div className="observation-row__title">{observation.title}</div>
        {evidence?.source_url ? (
          <a className="observation-row__source" href={evidence.source_url} target="_blank" rel="noreferrer">
            {evidence.source_name || evidence.source_url}
          </a>
        ) : (
          <span className="observation-row__source">{evidence?.source_name || 'No source link'}</span>
        )}
      </div>
      <div className="observation-row__scores">
        <span>CONF {pct(observation.confidence_score)}</span>
        {observation.candidate_event_type && <span>{observation.candidate_event_type}</span>}
      </div>
      <div className="observation-row__actions">
        <button type="button" disabled={busy || !canPromote} onClick={() => onPromote(observation.id)}>Promote</button>
        <button type="button" disabled={busy} onClick={() => onDismiss(observation.id)}>Dismiss</button>
      </div>
      <form
        className="observation-row__link"
        onSubmit={(event) => {
          event.preventDefault()
          const parsed = Number(eventId)
          if (Number.isInteger(parsed) && parsed > 0) onLink(observation.id, parsed)
        }}
      >
        <input
          value={eventId}
          onChange={(event) => setEventId(event.target.value)}
          inputMode="numeric"
          placeholder="Event ID"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !eventId}>Link</button>
      </form>
    </div>
  )
}

export default function ObservationReview({
  observations,
  loading,
  busyId,
  error,
  onPromote,
  onDismiss,
  onLink,
}) {
  return (
    <section className="observation-review">
      <div className="panel-header">
        <span className="panel-header__title">Lead Review</span>
        <span className="panel-header__count">{observations.length}</span>
      </div>
      {error && <span className="observation-review__error">{error}</span>}
      <div className="observation-review__items">
        {loading && observations.length === 0 && (
          <span className="observation-review__empty">Loading leads…</span>
        )}
        {!loading && observations.length === 0 && (
          <span className="observation-review__empty">No leads waiting for review.</span>
        )}
        {observations.map(observation => (
          <ObservationRow
            key={observation.id}
            observation={observation}
            busy={busyId === observation.id}
            onPromote={onPromote}
            onDismiss={onDismiss}
            onLink={onLink}
          />
        ))}
      </div>
    </section>
  )
}
