import { useEffect, useMemo, useRef, useState } from 'react'
import {
  dismissObservation,
  fetchEventDetail,
  fetchEvents,
  fetchHotspotDetail,
  fetchHotspots,
  fetchHotspotTrend,
  fetchMapSignals,
  fetchObservations,
  fetchPriorities,
  fetchSystemStatus,
  linkObservation,
  promoteObservation,
} from './services/api.js'

import Shell from './components/layout/Shell.jsx'
import TopChrome from './components/layout/TopChrome.jsx'
import WorkspaceTabs from './components/layout/WorkspaceTabs.jsx'
import NavRail from './components/layout/NavRail.jsx'
import ControlPopover from './components/layout/ControlPopover.jsx'
import TelemetryBar from './components/layout/TelemetryBar.jsx'
import MapPanel from './components/map/MapPanel.jsx'
import RightRail from './components/workstation/RightRail.jsx'
import IncidentsDrawer from './components/workstation/IncidentsDrawer.jsx'

const DEFAULT_LAYERS = {
  events: true,
  hotspots: true,
  confirmedHeat: true,
  signalHeat: true,
}

function parseTime(value) {
  if (!value) return null
  const date = new Date(String(value).match(/Z$|[+-]\d{2}:\d{2}$/) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

function withinWindow(value, hours) {
  const date = parseTime(value)
  if (!date) return false
  return date.getTime() >= Date.now() - hours * 3600 * 1000
}

export default function App() {
  const [events, setEvents] = useState([])
  const [eventTotal, setEventTotal] = useState(0)
  const [eventsOffset, setEventsOffset] = useState(0)
  const [eventsHasMore, setEventsHasMore] = useState(false)
  const [eventsLoadingMore, setEventsLoadingMore] = useState(false)
  const [hotspots, setHotspots] = useState([])
  const [priorities, setPriorities] = useState([])
  const [systemStatus, setSystemStatus] = useState(null)
  const [observations, setObservations] = useState([])
  const [mapSignals, setMapSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [lastPollFailed, setLastPollFailed] = useState(false)

  const [selectedItem, setSelectedItem] = useState(null)
  const [hotspotDetail, setHotspotDetail] = useState(null)
  const [hotspotTrend, setHotspotTrend] = useState(null)
  const [hotspotDetailLoading, setHotspotDetailLoading] = useState(false)
  const [eventDetail, setEventDetail] = useState(null)
  const [eventDetailLoading, setEventDetailLoading] = useState(false)
  const pendingHotspotId = useRef(null)
  const pendingEventId = useRef(null)
  const selectedItemRef = useRef(null)

  const [activeTypes, setActiveTypes] = useState(new Set())
  const [activeTrends, setActiveTrends] = useState(new Set())
  const [minSeverity, setMinSeverity] = useState(0)
  const [minConfidence, setMinConfidence] = useState(0)
  const [timeWindow, setTimeWindow] = useState(24)
  const [layersVisible, setLayersVisible] = useState(DEFAULT_LAYERS)
  const [activePopover, setActivePopover] = useState(null)
  const [activeWorkspace, setActiveWorkspace] = useState('map')
  const [rightTab, setRightTab] = useState('priorities')
  const [signalFocus, setSignalFocus] = useState(null)

  const [observationsLoading, setObservationsLoading] = useState(false)
  const [observationBusyId, setObservationBusyId] = useState(null)
  const [observationError, setObservationError] = useState(null)

  function applyEventsPage(page) {
    setEvents(page.items)
    setEventTotal(page.total)
    setEventsOffset(page.items.length)
    setEventsHasMore(page.has_more)
  }

  function mergeEventsPage(page) {
    setEvents(prev => {
      const byId = new Map(page.items.map(event => [event.id, event]))
      for (const event of prev) {
        if (!byId.has(event.id)) byId.set(event.id, event)
      }
      return [...byId.values()]
    })
    setEventTotal(page.total)
    setEventsOffset(prev => Math.max(prev, page.items.length))
    setEventsHasMore(page.has_more)
  }

  function refreshObservations() {
    setObservationsLoading(true)
    return Promise.all([fetchObservations('lead'), fetchMapSignals()])
      .then(([obs, signals]) => {
        setObservations(obs)
        setMapSignals(signals)
        setObservationError(null)
      })
      .catch(error => {
        console.error('[Flashpoint] observations error:', error)
        setObservationError('Lead exceptions unavailable')
      })
      .finally(() => setObservationsLoading(false))
  }

  function refreshConfirmedData() {
    return Promise.all([
      fetchEvents(500, 0),
      fetchHotspots(),
      fetchPriorities(),
      fetchSystemStatus(),
      fetchMapSignals(),
    ]).then(([eventPage, hotspotRows, priorityRows, status, signals]) => {
      applyEventsPage(eventPage)
      setHotspots(hotspotRows)
      setPriorities(priorityRows)
      setSystemStatus(status)
      setMapSignals(signals)
      setLastUpdated(new Date())
      setLastPollFailed(false)
    })
  }

  useEffect(() => {
    Promise.all([
      fetchEvents(500, 0),
      fetchHotspots(),
      fetchPriorities(),
      fetchSystemStatus(),
      fetchObservations('lead'),
      fetchMapSignals(),
    ])
      .then(([eventPage, hotspotRows, priorityRows, status, obs, signals]) => {
        applyEventsPage(eventPage)
        setHotspots(hotspotRows)
        setPriorities(priorityRows)
        setSystemStatus(status)
        setObservations(obs)
        setMapSignals(signals)
        setLastUpdated(new Date())
      })
      .catch(error => {
        console.error('[Flashpoint] initial fetch error:', error)
        setLastPollFailed(true)
      })
      .finally(() => setLoading(false))

    const pollId = setInterval(() => {
      Promise.all([fetchEvents(500, 0), fetchHotspots(), fetchPriorities(), fetchSystemStatus(), fetchObservations('lead'), fetchMapSignals()])
        .then(([eventPage, hotspotRows, priorityRows, status, obs, signals]) => {
          mergeEventsPage(eventPage)
          setHotspots(hotspotRows)
          setPriorities(priorityRows)
          setSystemStatus(status)
          setObservations(obs)
          setMapSignals(signals)
          setLastUpdated(new Date())
          setLastPollFailed(false)

          const selected = selectedItemRef.current
          if (selected?.type === 'hotspot') {
            const stillExists = hotspotRows.find(row => row.id === selected.data.id)
            if (stillExists) setSelectedItem({ type: 'hotspot', data: stillExists })
          }
        })
        .catch(error => {
          console.error('[Flashpoint] poll error:', error)
          setLastPollFailed(true)
        })
    }, 60_000)

    return () => clearInterval(pollId)
  }, [])

  useEffect(() => { selectedItemRef.current = selectedItem }, [selectedItem])

  function clearSelection() {
    pendingHotspotId.current = null
    pendingEventId.current = null
    setSelectedItem(null)
    setHotspotDetail(null)
    setHotspotTrend(null)
    setHotspotDetailLoading(false)
    setEventDetail(null)
    setEventDetailLoading(false)
  }

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') {
        setActivePopover(null)
        setActiveWorkspace('map')
        clearSelection()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function handleSelect(item) {
    const same = selectedItem?.type === item.type && selectedItem?.data?.id === item.data.id
    if (same) {
      clearSelection()
      return
    }

    setSelectedItem(item)
    setRightTab('priorities')
    setActivePopover(null)

    if (item.type === 'hotspot') {
      const id = item.data.id
      pendingHotspotId.current = id
      pendingEventId.current = null
      setEventDetail(null)
      setEventDetailLoading(false)
      setHotspotDetail(null)
      setHotspotTrend(null)
      setHotspotDetailLoading(true)
      Promise.all([fetchHotspotDetail(id), fetchHotspotTrend(id, 24)])
        .then(([detail, trend]) => {
          if (pendingHotspotId.current === id) {
            setHotspotDetail(detail)
            setHotspotTrend(trend)
          }
        })
        .catch(error => {
          console.error('[Flashpoint] hotspot detail error:', error)
          if (pendingHotspotId.current === id) clearSelection()
        })
        .finally(() => {
          if (pendingHotspotId.current === id) setHotspotDetailLoading(false)
        })
    } else if (item.type === 'event') {
      const id = item.data.id
      pendingEventId.current = id
      pendingHotspotId.current = null
      setHotspotDetail(null)
      setHotspotTrend(null)
      setHotspotDetailLoading(false)
      setEventDetail(null)
      setEventDetailLoading(true)
      fetchEventDetail(id)
        .then(detail => {
          if (pendingEventId.current === id) setEventDetail(detail)
        })
        .catch(error => console.error('[Flashpoint] event detail error:', error))
        .finally(() => {
          if (pendingEventId.current === id) setEventDetailLoading(false)
        })
    }
  }

  function handleSignalSelect(focus) {
    setSignalFocus({ lat: focus.lat, lon: focus.lon })
    setActiveWorkspace('incidents')
    setActivePopover(null)
  }

  function handleSetWorkspace(workspace) {
    setActiveWorkspace(workspace)
    if (workspace === 'map') setSignalFocus(null)
  }

  function handleShowSources() {
    clearSelection()
    setRightTab('sources')
  }

  function handleLoadMore() {
    setEventsLoadingMore(true)
    fetchEvents(500, eventsOffset)
      .then(page => {
        setEvents(prev => {
          const seen = new Set(prev.map(event => event.id))
          return [...prev, ...page.items.filter(event => !seen.has(event.id))]
        })
        setEventsOffset(prev => prev + page.items.length)
        setEventsHasMore(page.has_more)
        setEventTotal(page.total)
      })
      .catch(error => console.error('[Flashpoint] load more error:', error))
      .finally(() => setEventsLoadingMore(false))
  }

  function toggleType(key) {
    setActiveTypes(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  function toggleTrend(key) {
    setActiveTrends(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  function toggleLayer(key) {
    setLayersVisible(prev => ({ ...prev, [key]: !prev[key] }))
  }

  function handlePromoteObservation(id) {
    setObservationBusyId(id)
    setObservationError(null)
    promoteObservation(id)
      .then(() => Promise.all([refreshObservations(), refreshConfirmedData()]))
      .catch(error => {
        console.error('[Flashpoint] promote observation error:', error)
        setObservationError('Promote failed')
      })
      .finally(() => setObservationBusyId(null))
  }

  function handleDismissObservation(id) {
    setObservationBusyId(id)
    setObservationError(null)
    dismissObservation(id)
      .then(() => refreshObservations())
      .catch(error => {
        console.error('[Flashpoint] dismiss observation error:', error)
        setObservationError('Dismiss failed')
      })
      .finally(() => setObservationBusyId(null))
  }

  function handleLinkObservation(id, eventId) {
    setObservationBusyId(id)
    setObservationError(null)
    linkObservation(id, eventId)
      .then(() => Promise.all([refreshObservations(), refreshConfirmedData()]))
      .catch(error => {
        console.error('[Flashpoint] link observation error:', error)
        setObservationError('Link failed')
      })
      .finally(() => setObservationBusyId(null))
  }

  const filteredEvents = useMemo(() => events.filter(event => {
    if (!withinWindow(event.occurred_at, timeWindow)) return false
    if (activeTypes.size > 0 && !activeTypes.has(event.event_type)) return false
    if (event.severity_score < minSeverity) return false
    if (event.confidence_score < minConfidence) return false
    if (activeTrends.size > 0 && !activeTrends.has(event.trend_state)) return false
    if (event.source_name === 'gdelt' && event.source_count < 2) return false
    return true
  }), [events, timeWindow, activeTypes, minSeverity, minConfidence, activeTrends])

  const filteredSignals = useMemo(() => mapSignals.filter(signal => {
    if (!withinWindow(signal.observed_at, timeWindow)) return false
    if (activeTypes.size > 0 && !activeTypes.has(signal.candidate_event_type)) return false
    if (signal.severity_score < minSeverity) return false
    if (signal.confidence_score < minConfidence) return false
    return true
  }), [mapSignals, timeWindow, activeTypes, minSeverity, minConfidence])

  const filteredHotspots = useMemo(
    () => activeTrends.size === 0 ? hotspots : hotspots.filter(hotspot => activeTrends.has(hotspot.trend_state)),
    [hotspots, activeTrends],
  )

  const filteredPriorities = useMemo(
    () => activeTrends.size === 0 ? priorities : priorities.filter(priority => activeTrends.has(priority.trend_state)),
    [priorities, activeTrends],
  )

  const eventTypeCounts = useMemo(() => {
    const counts = {}
    for (const event of events) {
      if (!withinWindow(event.occurred_at, timeWindow)) continue
      if (event.severity_score < minSeverity) continue
      if (event.confidence_score < minConfidence) continue
      if (activeTrends.size > 0 && !activeTrends.has(event.trend_state)) continue
      if (event.source_name === 'gdelt' && event.source_count < 2) continue
      counts[event.event_type] = (counts[event.event_type] || 0) + 1
    }
    return counts
  }, [events, timeWindow, minSeverity, minConfidence, activeTrends])

  const activeFilterCount = (
    activeTypes.size
    + activeTrends.size
    + (minSeverity > 0 ? 1 : 0)
    + (minConfidence > 0 ? 1 : 0)
    + (timeWindow !== 24 ? 1 : 0)
  )

  return (
    <Shell
      rightExpanded={Boolean(selectedItem)}
      top={
        <>
          <TopChrome
            systemStatus={systemStatus}
            lastPollFailed={lastPollFailed}
            timeWindow={timeWindow}
            onSetTimeWindow={setTimeWindow}
            openPopover={setActivePopover}
            activePopover={activePopover}
          />
          <ControlPopover
            kind={activePopover}
            activeTypes={activeTypes}
            onToggleType={toggleType}
            onClearTypes={() => setActiveTypes(new Set())}
            minSeverity={minSeverity}
            onSetSeverity={setMinSeverity}
            minConfidence={minConfidence}
            onSetConfidence={setMinConfidence}
            activeTrends={activeTrends}
            onToggleTrend={toggleTrend}
            layersVisible={layersVisible}
            onToggleLayer={toggleLayer}
            eventTypeCounts={eventTypeCounts}
          />
        </>
      }
      tabs={
        <WorkspaceTabs
          activeWorkspace={activeWorkspace}
          onSetWorkspace={handleSetWorkspace}
          counts={{
            events: eventTotal,
            visibleEvents: filteredEvents.length,
            signals: filteredSignals.length,
            hotspots: filteredHotspots.length,
          }}
        />
      }
      nav={
        <NavRail
          activeWorkspace={activeWorkspace}
          onSetWorkspace={handleSetWorkspace}
          onShowSources={handleShowSources}
          counts={{ leads: observations.length }}
        />
      }
      map={
        <MapPanel
          events={filteredEvents}
          hotspots={filteredHotspots}
          signals={filteredSignals}
          selectedItem={selectedItem}
          onSelect={handleSelect}
          onSignalSelect={handleSignalSelect}
          layersVisible={layersVisible}
        />
      }
      right={
        <RightRail
          activeTab={rightTab}
          onSetTab={setRightTab}
          priorities={filteredPriorities}
          selectedItem={selectedItem}
          onSelect={handleSelect}
          detailProps={{
            onClose: clearSelection,
            hotspotDetail,
            hotspotDetailLoading,
            hotspotTrend,
            eventDetail,
            eventDetailLoading,
            signals: filteredSignals,
          }}
          observations={observations}
          observationsLoading={observationsLoading}
          observationBusyId={observationBusyId}
          observationError={observationError}
          onPromoteObservation={handlePromoteObservation}
          onDismissObservation={handleDismissObservation}
          onLinkObservation={handleLinkObservation}
          systemStatus={systemStatus}
        />
      }
      drawer={
        <IncidentsDrawer
          open={activeWorkspace === 'incidents'}
          onClose={() => handleSetWorkspace('map')}
          events={filteredEvents}
          loadedCount={events.length}
          total={eventTotal}
          hasMore={eventsHasMore}
          onLoadMore={handleLoadMore}
          loadingMore={eventsLoadingMore}
          selectedItem={selectedItem}
          onSelect={handleSelect}
          signals={filteredSignals}
          signalFocus={signalFocus}
        />
      }
      status={
        <TelemetryBar
          systemStatus={systemStatus}
          lastUpdated={lastUpdated}
          lastPollFailed={lastPollFailed}
          activeFilterCount={activeFilterCount}
          loading={loading}
        />
      }
    />
  )
}
