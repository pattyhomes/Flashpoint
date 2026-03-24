import { useState, useEffect, useMemo } from 'react'
import { fetchEvents, fetchHotspots, fetchPriorities, fetchSystemStatus } from './services/api.js'

import Shell from './components/layout/Shell.jsx'
import StatusBar from './components/layout/StatusBar.jsx'
import MapPanel from './components/map/MapPanel.jsx'
import FilterRail from './components/filters/FilterRail.jsx'
import PriorityList from './components/priorities/PriorityList.jsx'
import DetailPane from './components/detail/DetailPane.jsx'
import EventFeed from './components/feed/EventFeed.jsx'

export default function App() {
  const [events, setEvents]       = useState([])
  const [hotspots, setHotspots]   = useState([])
  const [priorities, setPriorities] = useState([])
  const [loading, setLoading]         = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [systemStatus, setSystemStatus] = useState(null)

  const [selectedItem, setSelectedItem] = useState(null)
  const [activeTypes, setActiveTypes]   = useState(new Set())
  const [layersVisible, setLayersVisible] = useState({ events: true, hotspots: true, heatmap: false })
  const [minSeverity,   setMinSeverity]   = useState(0)
  const [minConfidence, setMinConfidence] = useState(0)
  const [activeTrends,  setActiveTrends]  = useState(new Set())

  // Fetch all data once on mount
  useEffect(() => {
    Promise.all([fetchEvents(), fetchHotspots(), fetchPriorities(), fetchSystemStatus()])
      .then(([ev, hs, pr, status]) => {
        setEvents(ev)
        setHotspots(hs)
        setPriorities(pr)
        setSystemStatus(status)
        setLastUpdated(new Date())
      })
      .catch(err => console.error('[Flashpoint] fetch error:', err))
      .finally(() => setLoading(false))
  }, [])

  // Escape key to dismiss selection
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelectedItem(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Toggle-to-deselect
  function handleSelect(item) {
    setSelectedItem(prev =>
      prev?.type === item.type && prev?.data?.id === item.data.id ? null : item
    )
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
      if (!filteredHotspots.find(h => h.id === selectedItem.data.id)) setSelectedItem(null)
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
            onClose={() => setSelectedItem(null)}
            events={filteredEvents}
          />
        </>
      }
      bottom={
        <EventFeed
          events={filteredEvents}
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
