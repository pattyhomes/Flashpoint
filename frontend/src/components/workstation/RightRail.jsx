import DetailPane from '../detail/DetailPane.jsx'
import PriorityList from '../priorities/PriorityList.jsx'
import ObservationReview from '../review/ObservationReview.jsx'

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
          <div className="source-health">
            <div className="rail-section-title">
              <span>Feeds</span>
              <b>{systemStatus?.last_run_status || 'idle'}</b>
            </div>
            <div className="feed-row">
              <span>Ingest Pipeline</span>
              <b>{systemStatus?.last_run_status || 'unknown'}</b>
            </div>
            <div className="feed-row">
              <span>Confirmed Events</span>
              <b>{systemStatus?.event_count ?? 0}</b>
            </div>
            <div className="feed-row">
              <span>Mapped Signals</span>
              <b>{systemStatus?.mapped_signal_count ?? 0}</b>
            </div>
          </div>
          <ObservationReview
            observations={observations}
            loading={observationsLoading}
            busyId={observationBusyId}
            error={observationError}
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
