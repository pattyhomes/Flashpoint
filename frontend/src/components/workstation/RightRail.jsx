import DetailPane from '../detail/DetailPane.jsx'
import PriorityList from '../priorities/PriorityList.jsx'
import ObservationReview from '../review/ObservationReview.jsx'
import { relativeTime } from '../../utils/time.js'

function labelize(value) {
  if (!value) return 'Uncategorized'
  return value.replaceAll('_', ' ')
}

function formatCount(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '0'
}

function ratioParts(fetched, accepted, rejected) {
  const total = Math.max(Number(fetched) || 0, (Number(accepted) || 0) + (Number(rejected) || 0), 1)
  return {
    accepted: Math.max(0, Math.min(100, ((Number(accepted) || 0) / total) * 100)),
    rejected: Math.max(0, Math.min(100, ((Number(rejected) || 0) / total) * 100)),
  }
}

function SourceRatioBar({ fetched, accepted, rejected, label }) {
  const parts = ratioParts(fetched, accepted, rejected)
  const acceptedWidth = parts.accepted
  const rejectedWidth = parts.rejected
  const unclassifiedWidth = Math.max(0, 100 - acceptedWidth - rejectedWidth)

  return (
    <span
      className="source-ratio-bar"
      aria-label={`${label}: ${formatCount(fetched)} fetched, ${formatCount(accepted)} accepted, ${formatCount(rejected)} rejected`}
      title={`${formatCount(fetched)} fetched / ${formatCount(accepted)} accepted / ${formatCount(rejected)} rejected`}
    >
      <i className="source-ratio-bar__accepted" style={{ width: `${acceptedWidth}%` }} />
      <i className="source-ratio-bar__rejected" style={{ width: `${rejectedWidth}%` }} />
      {unclassifiedWidth > 0 && <i className="source-ratio-bar__remainder" style={{ width: `${unclassifiedWidth}%` }} />}
    </span>
  )
}

function SourceHealth({ sourceStatus, systemStatus, sourceRunBusy, onRunSource }) {
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
        ) : sources.map(source => {
          const accepted = source.observations_inserted || 0
          const fetched = source.records_fetched || 0
          const acceptanceRate = fetched > 0 ? Math.round((accepted / fetched) * 100) : 0
          const rejectEntries = Object.entries(source.reject_counts || {}).sort((a, b) => b[1] - a[1])
          const topReject = rejectEntries[0]
          const samples = source.sample_records || []
          const breakdown = source.source_breakdown || []

          return (
            <div
              className={`source-row source-row--${source.status}${source.stale ? ' source-row--stale' : ''}`}
              key={source.source_name}
            >
              <div className="source-row__main">
                <div>
                  <b>{labelize(source.source_name)}</b>
                  <span>{source.last_error || (source.stale ? 'stale feed' : source.last_run_at ? 'fresh' : 'not scheduled')}</span>
                </div>
                <div className="source-row__quality">
                  <span>{acceptanceRate}% accepted</span>
                  {topReject && <span>{labelize(topReject[0])}: {formatCount(topReject[1])}</span>}
                </div>
                {source.runnable && (
                  <button
                    type="button"
                    className="source-row__run"
                    disabled={sourceRunBusy === source.source_name}
                    onClick={() => onRunSource(source.source_name)}
                  >
                    {sourceRunBusy === source.source_name ? 'RUNNING' : 'RUN NOW'}
                  </button>
                )}
                {samples.length > 0 && (
                  <div className="source-row__samples">
                    {samples.slice(0, 3).map((sample, index) => (
                      <div className="source-sample" key={`${source.source_name}-${index}`}>
                        <b>{labelize(sample.category)}</b>
                        <span>{sample.title || sample.reason || 'Sample record'}</span>
                      </div>
                    ))}
                  </div>
                )}
                {breakdown.length > 0 && (
                  <div className="source-breakdown">
                    {breakdown.slice(0, 4).map(feed => (
                      <div className="source-breakdown__row" key={`${source.source_name}-${feed.source_name}`}>
                        <div className="source-breakdown__meta">
                          <b>{feed.source_name || 'Feed'}</b>
                          <span>F {formatCount(feed.records_fetched)} A {formatCount(feed.observations_inserted)} R {formatCount(feed.records_rejected)}</span>
                        </div>
                        <SourceRatioBar
                          fetched={feed.records_fetched}
                          accepted={feed.observations_inserted}
                          rejected={feed.records_rejected}
                          label={feed.source_name || 'Feed'}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <dl>
                <dt>F</dt><dd>{formatCount(source.records_fetched)}</dd>
                <dt>A</dt><dd>{formatCount(source.observations_inserted)}</dd>
                <dt>R</dt><dd>{formatCount(source.records_rejected)}</dd>
              </dl>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SourceRuns({ runs, loading }) {
  return (
    <div className="source-runs">
      <div className="rail-section-title">
        <span>Recent Runs</span>
        <b>{loading ? 'sync' : formatCount(runs.length)}</b>
      </div>
      <div className="source-runs__list">
        {runs.length === 0 ? (
          <span className="empty-note">No run history yet.</span>
        ) : runs.slice(0, 8).map(run => (
          <div className={`source-run source-run--${run.status}`} key={run.id}>
            <div>
              <b>{labelize(run.source_name)}</b>
              <span>{relativeTime(run.finished_at || run.started_at)}</span>
              <SourceRatioBar
                fetched={run.records_fetched}
                accepted={run.observations_inserted}
                rejected={run.records_rejected}
                label={run.source_name || 'source run'}
              />
            </div>
            <dl>
              <dt>F</dt><dd>{formatCount(run.records_fetched)}</dd>
              <dt>A</dt><dd>{formatCount(run.observations_inserted)}</dd>
              <dt>R</dt><dd>{formatCount(run.records_rejected)}</dd>
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
  priorityTrends,
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
  sourceRuns,
  sourceRunsLoading,
  sourceRunBusy,
  sourceRunError,
  onRunSource,
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
          {sourceRunError && <span className="empty-note empty-note--error">{sourceRunError}</span>}
          <SourceHealth
            sourceStatus={sourceStatus}
            systemStatus={systemStatus}
            sourceRunBusy={sourceRunBusy}
            onRunSource={onRunSource}
          />
          <SourceRuns runs={sourceRuns || []} loading={sourceRunsLoading} />
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
        <PriorityList
          priorities={priorities}
          priorityTrends={priorityTrends}
          selectedItem={selectedItem}
          onSelect={onSelect}
        />
      )}
    </div>
  )
}
