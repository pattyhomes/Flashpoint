import DetailPane from '../detail/DetailPane.jsx'
import PriorityList from '../priorities/PriorityList.jsx'
import ObservationReview from '../review/ObservationReview.jsx'

function labelize(value) {
  if (!value) return 'Uncategorized'
  return value.replaceAll('_', ' ')
}

function formatCount(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '0'
}

function SourceHealth({ sourceStatus, systemStatus }) {
  const sources = sourceStatus?.sources || []
  const totalSources = sources.length || systemStatus?.source_count || 0
  const unhealthy = sources.filter(source => source.status !== 'success').length || systemStatus?.unhealthy_source_count || 0

  return (
    <div className="source-health">
      <div className="rail-section-title">
        <span>Feeds</span>
        <b>{unhealthy > 0 ? `${unhealthy} attention` : 'nominal'}</b>
      </div>
      <div className="source-summary">
        <div>
          <span>Sources</span>
          <b>{totalSources}</b>
        </div>
        <div>
          <span>Accepted</span>
          <b>{formatCount(sources.reduce((sum, source) => sum + (source.observations_inserted || 0), 0))}</b>
        </div>
        <div>
          <span>Rejected</span>
          <b>{formatCount(sources.reduce((sum, source) => sum + (source.records_rejected || 0), 0))}</b>
        </div>
      </div>
      <div className="source-list">
        {sources.length === 0 ? (
          <span className="empty-note">No source runs yet.</span>
        ) : sources.map(source => (
          <div
            className={`source-row source-row--${source.status}${source.stale ? ' source-row--stale' : ''}`}
            key={source.source_name}
          >
            <div>
              <b>{labelize(source.source_name)}</b>
              <span>{source.last_error || (source.stale ? 'stale feed' : source.last_run_at ? 'fresh' : 'not scheduled')}</span>
            </div>
            <dl>
              <dt>F</dt><dd>{formatCount(source.records_fetched)}</dd>
              <dt>A</dt><dd>{formatCount(source.observations_inserted)}</dd>
              <dt>R</dt><dd>{formatCount(source.records_rejected)}</dd>
            </dl>
          </div>
        ))}
      </div>
    </div>
  )
}

function ExceptionFilters({ counts, activeCategory, onSetCategory }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1])

  return (
    <div className="exception-filters">
      <div className="rail-section-title">
        <span>Exception Buckets</span>
        <b>{formatCount(entries.reduce((sum, [, count]) => sum + count, 0))}</b>
      </div>
      <div className="exception-filter-row">
        <button
          type="button"
          className={!activeCategory ? 'is-active' : ''}
          onClick={() => onSetCategory(null)}
        >
          All
        </button>
        {entries.map(([category, count]) => (
          <button
            type="button"
            key={category}
            className={activeCategory === category ? 'is-active' : ''}
            onClick={() => onSetCategory(category)}
          >
            <span>{labelize(category)}</span>
            <b>{count}</b>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function RightRail({
  activeTab,
  onSetTab,
  priorities,
  selectedItem,
  onSelect,
  detailProps,
  observations,
  observationsLoading,
  observationBusyId,
  observationError,
  onPromoteObservation,
  onDismissObservation,
  onLinkObservation,
  systemStatus,
  sourceStatus,
  activeExceptionCategory,
  onSetExceptionCategory,
}) {
  const inDetail = Boolean(selectedItem)

  return (
    <div className={`right-rail${inDetail ? ' right-rail--detail' : ''}`}>
      {!inDetail && (
        <div className="right-rail__tabs" role="tablist" aria-label="Right rail">
          <button
            type="button"
            className={activeTab === 'priorities' ? 'is-active' : ''}
            onClick={() => onSetTab('priorities')}
          >
            PRIORITIES
          </button>
          <button
            type="button"
            className={activeTab === 'sources' ? 'is-active' : ''}
            onClick={() => onSetTab('sources')}
          >
            SOURCES
            {observations.length > 0 && <b>{observations.length}</b>}
          </button>
        </div>
      )}

      {inDetail ? (
        <DetailPane {...detailProps} item={selectedItem} />
      ) : activeTab === 'sources' ? (
        <div className="sources-rail">
          <SourceHealth sourceStatus={sourceStatus} systemStatus={systemStatus} />
          <ExceptionFilters
            counts={sourceStatus?.exception_counts || systemStatus?.exception_counts}
            activeCategory={activeExceptionCategory}
            onSetCategory={onSetExceptionCategory}
          />
          <ObservationReview
            observations={observations}
            loading={observationsLoading}
            busyId={observationBusyId}
            error={observationError}
            activeExceptionCategory={activeExceptionCategory}
            onPromote={onPromoteObservation}
            onDismiss={onDismissObservation}
            onLink={onLinkObservation}
          />
        </div>
      ) : (
        <PriorityList priorities={priorities} selectedItem={selectedItem} onSelect={onSelect} />
      )}
    </div>
  )
}
