import { useState } from 'react'
import { relativeTime } from '../../utils/time.js'

function pct(value) {
  return Math.round((value || 0) * 100)
}

function labelize(value) {
  if (!value) return 'unclassified'
  return value.replaceAll('_', ' ')
}

function LeadRow({ observation, busy, onPromote, onDismiss, onLink }) {
  const [eventId, setEventId] = useState('')
  const evidence = observation.evidence
  const canPromote = Boolean(
    observation.latitude
    && observation.longitude
    && observation.observed_at
    && observation.candidate_event_type
    && (observation.location_confidence ?? 1) >= 0.75
  )

  return (
    <article className="lead-card">
      <div className="lead-card__top">
        <span className={`trust-chip trust-chip--${evidence?.trust_tier || 'weak'}`}>
          {evidence?.trust_tier || 'weak'}
        </span>
        <span>{evidence?.source_type || 'source'}</span>
        <span>{relativeTime(observation.observed_at || evidence?.published_at)}</span>
        <b>CONF {pct(observation.confidence_score)}</b>
      </div>
      {observation.exception_category && (
        <div className="lead-card__exception">
          <b>{labelize(observation.exception_category)}</b>
          <span>{observation.exception_detail || observation.location_reason || 'needs review'}</span>
        </div>
      )}
      <div className="lead-card__title">{observation.title}</div>
      <div className="lead-card__meta">
        <span>{[observation.city, observation.state].filter(Boolean).join(', ') || observation.country}</span>
        <span>{observation.candidate_event_type || 'context'} / LOC {pct(observation.location_confidence ?? 1)}</span>
      </div>
      {evidence?.source_url ? (
        <a className="lead-card__source" href={evidence.source_url} target="_blank" rel="noreferrer">
          {evidence.source_name || evidence.source_url}
        </a>
      ) : (
        <span className="lead-card__source">{evidence?.source_name || 'No source link'}</span>
      )}

      <details className="lead-card__advanced">
        <summary>Advanced Review</summary>
        <div className="lead-card__actions">
          <button type="button" disabled={busy || !canPromote} onClick={() => onPromote(observation.id)}>Promote</button>
          <button type="button" disabled={busy} onClick={() => onDismiss(observation.id)}>Dismiss</button>
        </div>
        <form
          className="lead-card__link"
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
      </details>
    </article>
  )
}

export default function ObservationReview({
  observations,
  loading,
  busyId,
  error,
  activeExceptionCategory,
  onPromote,
  onDismiss,
  onLink,
}) {
  return (
    <section className="lead-review">
      <div className="rail-section-title">
        <span>Exceptions</span>
        <b>{activeExceptionCategory ? labelize(activeExceptionCategory) : observations.length}</b>
      </div>
      {error && <span className="empty-note empty-note--error">{error}</span>}
      <div className="lead-review__list">
        {loading && observations.length === 0 && <span className="empty-note">Loading leads.</span>}
        {!loading && observations.length === 0 && <span className="empty-note">No exceptions waiting.</span>}
        {observations.map(observation => (
          <LeadRow
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
