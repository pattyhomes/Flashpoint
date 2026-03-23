import { useState, useEffect, useMemo } from 'react'
import { fetchEvents, fetchHotspots, fetchPriorities } from './services/api.js'

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
  const [loading, setLoading]     = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const [selectedItem, setSelectedItem] = useState(null)
  const [activeTypes, setActiveTypes]   = useState(new Set())
  const [layersVisible, setLayersVisible] = useState({ events: true, hotspots: true, heatmap: false })

  // Fetch all data once on mount
  useEffect(() => {
    Promise.all([fetchEvents(), fetchHotspots(), fetchPriorities()])
      .then(([ev, hs, pr]) => {
        setEvents(ev)
        setHotspots(hs)
        setPriorities(pr)
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

  const filteredEvents = useMemo(
    () => activeTypes.size === 0 ? events : events.filter(e => activeTypes.has(e.event_type)),
    [events, activeTypes]
  )

  return (
    <Shell
      left={
        <FilterRail
          activeTypes={activeTypes}
          onToggle={handleToggleType}
          onClear={() => setActiveTypes(new Set())}
          layersVisible={layersVisible}
          onToggleLayer={handleToggleLayer}
        />
      }
      map={
        <MapPanel
          events={filteredEvents}
          hotspots={hotspots}
          selectedItem={selectedItem}
          onSelect={handleSelect}
          layersVisible={layersVisible}
        />
      }
      right={
        <>
          <PriorityList
            priorities={priorities}
            selectedItem={selectedItem}
            onSelect={handleSelect}
          />
          <DetailPane
            item={selectedItem}
            onClose={() => setSelectedItem(null)}
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
        <StatusBar lastUpdated={lastUpdated} loading={loading} />
      }
    />
  )
}
