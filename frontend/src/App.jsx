import { useState, useEffect, useRef, useMemo } from 'react'
import { fetchEvents, fetchHotspots, fetchHotspotDetail, fetchPriorities, fetchSystemStatus } from './services/api.js'

import Shell from './components/layout/Shell.jsx'
import StatusBar from './components/layout/StatusBar.jsx'
import MapPanel from './components/map/MapPanel.jsx'
import FilterRail from './components/filters/FilterRail.jsx'
import PriorityList from './components/priorities/PriorityList.jsx'
import DetailPane from './components/detail/DetailPane.jsx'
import EventFeed from './components/feed/EventFeed.jsx'

export default function App() {
  const [events, setEvents]       = useState([])
  const [eventTotal,        setEventTotal]        = useState(0)
  const [eventsOffset,      setEventsOffset]      = useState(0)
  const [eventsHasMore,     setEventsHasMore]     = useState(false)
  const [eventsLoadingMore, setEventsLoadingMore] = useState(false)
  const [hotspots, setHotspots]   = useState([])
  const [priorities, setPriorities] = useState([])
  const [loading, setLoading]         = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [systemStatus, setSystemStatus] = useState(null)

  const [selectedItem, setSelectedItem] = useState(null)
  const [hotspotDetail, setHotspotDetail]               = useState(null)
  const [hotspotDetailLoading, setHotspotDetailLoading] = useState(false)
  const pendingHotspotId = useRef(null)
  const [activeTypes, setActiveTypes]   = useState(new Set())
  const [layersVisible, setLayersVisible] = useState({ events: true, hotspots: true, heatmap: false })
  const [minSeverity,   setMinSeverity]   = useState(0)
  const [minConfidence, setMinConfidence] = useState(0)
  const [activeTrends,  setActiveTrends]  = useState(new Set())

  // Fetch all data once on mount
  useEffect(() => {
    Promise.all([fetchEvents(500, 0), fetchHotspots(), fetchPriorities(), fetchSystemStatus()])
      .then(([evPage, hs, pr, status]) => {
        setEvents(evPage.items)
        setEventTotal(evPage.total)
        setEventsOffset(evPage.items.length)
        setEventsHasMore(evPage.has_more)
        setHotspots(hs)
        setPriorities(pr)
        setSystemStatus(status)
        setLastUpdated(new Date())
      })
      .catch(err => console.error('[Flashpoint] fetch error:', err))
      .finally(() => setLoading(false))
  }, [])

  // Load the next page of events and merge by id to prevent duplicates
  function handleLoadMore() {
    setEventsLoadingMore(true)
    fetchEvents(500, eventsOffset)
      .then(evPage => {
        setEvents(prev => {
          const seen = new Set(prev.map(e => e.id))
          const fresh = evPage.items.filter(e => !seen.has(e.id))
          return [...prev, ...fresh]
        })
        setEventsOffset(prev => prev + evPage.items.length)
        setEventsHasMore(evPage.has_more)
        setEventTotal(evPage.total)
      })
      .catch(err => console.error('[Flashpoint] load more error:', err))
      .finally(() => setEventsLoadingMore(false))
  }

  // Escape key to dismiss selection
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        pendingHotspotId.current = null
        setSelectedItem(null)
        setHotspotDetail(null)
        setHotspotDetailLoading(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Toggle-to-deselect; load hotspot detail from backend when a hotspot is selected
  function handleSelect(item) {
    const isSame = selectedItem?.type === item.type && selectedItem?.data?.id === item.data.id
    const next = isSame ? null : item
    setSelectedItem(next)

    if (next?.type === 'hotspot') {
      const id = next.data.id
      pendingHotspotId.current = id
      setHotspotDetail(null)
      setHotspotDetailLoading(true)
      fetchHotspotDetail(id)
        .then(detail => {
          if (pendingHotspotId.current === id) setHotspotDetail(detail)
        })
        .catch(err => {
          if (pendingHotspotId.current === id)
            console.error('[Flashpoint] hotspot detail error:', err)
        })
        .finally(() => {
          if (pendingHotspotId.current === id) setHotspotDetailLoading(false)
        })
    } else {
      pendingHotspotId.current = null
      setHotspotDetail(null)
      setHotspotDetailLoading(false)
    }
  }

  // Toggle map layer visibility
  function handleToggleLayer(key) {
    setLayersVisible(prev => ({ ...prev, [key]: !prev[key] }))
  }

  // Filter event types
  function handleToggleType(key) {
    setActiveTypes(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // Filter trend state
  function handleToggleTrend(key) {
    setActiveTrends(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const filteredEvents = useMemo(() => events.filter(e => {
    if (activeTypes.size > 0  && !activeTypes.has(e.event_type))    return false
    if (e.severity_score   < minSeverity)                            return false
    if (e.confidence_score < minConfidence)                          return false
    if (activeTrends.size  > 0 && !activeTrends.has(e.trend_state)) return false
    if (e.source_name === 'gdelt' && e.source_count < 2)             return false  // GDELT quality gate
    return true
  }), [events, activeTypes, minSeverity, minConfidence, activeTrends])

  const filteredHotspots = useMemo(
    () => activeTrends.size === 0 ? hotspots : hotspots.filter(h => activeTrends.has(h.trend_state)),
    [hotspots, activeTrends]
  )

  const filteredPriorities = useMemo(
    () => activeTrends.size === 0 ? priorities : priorities.filter(p => activeTrends.has(p.trend_state)),
    [priorities, activeTrends]
  )

  // Clear selection when the selected item is filtered out
  useEffect(() => {
    if (!selectedItem) return
    if (selectedItem.type === 'event') {
      if (!filteredEvents.find(e => e.id === selectedItem.data.id)) setSelectedItem(null)
    } else {
      if (!filteredHotspots.find(h => h.id === selectedItem.data.id)) {
        pendingHotspotId.current = null
        setSelectedItem(null)
        setHotspotDetail(null)
        setHotspotDetailLoading(false)
      }
    }
  }, [filteredEvents, filteredHotspots, selectedItem])

  return (
    <Shell
      left={
        <FilterRail
          activeTypes={activeTypes}     onToggle={handleToggleType}
          onClear={() => setActiveTypes(new Set())}
          layersVisible={layersVisible} onToggleLayer={handleToggleLayer}
          minSeverity={minSeverity}     onSetSeverity={setMinSeverity}
          minConfidence={minConfidence} onSetConfidence={setMinConfidence}
          activeTrends={activeTrends}   onToggleTrend={handleToggleTrend}
        />
      }
      map={
        <MapPanel
          events={filteredEvents}
          hotspots={filteredHotspots}
          selectedItem={selectedItem}
          onSelect={handleSelect}
          layersVisible={layersVisible}
        />
      }
      right={
        <>
          <PriorityList
            priorities={filteredPriorities}
            selectedItem={selectedItem}
            onSelect={handleSelect}
          />
          <DetailPane
            item={selectedItem}
            onClose={() => {
              pendingHotspotId.current = null
              setSelectedItem(null)
              setHotspotDetail(null)
              setHotspotDetailLoading(false)
            }}
            hotspotDetail={hotspotDetail}
            hotspotDetailLoading={hotspotDetailLoading}
          />
        </>
      }
      bottom={
        <EventFeed
          events={filteredEvents}
          loadedCount={events.length}
          total={eventTotal}
          hasMore={eventsHasMore}
          onLoadMore={handleLoadMore}
          loadingMore={eventsLoadingMore}
          selectedItem={selectedItem}
          onSelect={handleSelect}
        />
      }
      status={
        <StatusBar lastUpdated={lastUpdated} loading={loading} systemStatus={systemStatus} />
      }
    />
  )
}
