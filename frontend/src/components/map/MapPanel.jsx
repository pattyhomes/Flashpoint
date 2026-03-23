import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const US_CENTER = [-98, 38.5]
const US_ZOOM   = 3.8

function severityColor(score) {
  // Matches the shell's severity scale
  return ['step', ['get', 'severity_score'],
    '#22c55e', 0.4,
    '#eab308', 0.6,
    '#f59e0b', 0.8,
    '#ef4444',
  ]
}

function trendColor() {
  return ['match', ['get', 'trend_state'],
    'escalating', '#ef4444',
    'declining',  '#22c55e',
    /* default */ '#9aa0b0',
  ]
}

function toEventsGeoJSON(events) {
  return {
    type: 'FeatureCollection',
    features: events.map(e => ({
      type: 'Feature',
      id: e.id,
      geometry: { type: 'Point', coordinates: [e.longitude, e.latitude] },
      properties: { id: e.id, severity_score: e.severity_score, event_type: e.event_type },
    })),
  }
}

function toHotspotsGeoJSON(hotspots) {
  return {
    type: 'FeatureCollection',
    features: hotspots.map(h => ({
      type: 'Feature',
      id: h.id,
      geometry: { type: 'Point', coordinates: [h.centroid_lon, h.centroid_lat] },
      properties: { id: h.id, trend_state: h.trend_state || 'stable' },
    })),
  }
}

const EMPTY_FC = { type: 'FeatureCollection', features: [] }

export default function MapPanel({ events = [], hotspots = [], selectedItem, onSelect, layersVisible = { events: true, hotspots: true, heatmap: false } }) {
  const containerRef = useRef(null)
  const mapRef       = useRef(null)
  const loadedRef    = useRef(false)

  // Keep refs current so handlers registered once always see latest data
  const eventsRef    = useRef(events)
  const hotspotsRef  = useRef(hotspots)
  const onSelectRef  = useRef(onSelect)
  eventsRef.current   = events
  hotspotsRef.current = hotspots
  onSelectRef.current = onSelect

  // ── Initialize map once ──────────────────────────────────────────────────
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: US_CENTER,
      zoom: US_ZOOM,
      attributionControl: false,
    })

    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      'bottom-left'
    )
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      'bottom-right'
    )

    map.on('load', () => {
      loadedRef.current = true

      // ── Events ─────────────────────────────────────────────────────────
      map.addSource('events', { type: 'geojson', data: toEventsGeoJSON(eventsRef.current) })

      // ── Heatmap (below event circles) ───────────────────────────────────
      map.addLayer({
        id: 'heatmap-layer',
        type: 'heatmap',
        source: 'events',
        layout: { visibility: 'none' },
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'severity_score'],
            0, 0.5,
            1, 1.5,
          ],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'],
            3, 20,
            8, 35,
          ],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'],
            3, 1,
            8, 2,
          ],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0,    'rgba(0,0,0,0)',
            0.25, 'rgba(234,179,8,0.0)',
            0.45, 'rgba(245,158,11,0.35)',
            0.65, 'rgba(239,68,68,0.50)',
            0.85, 'rgba(239,68,68,0.65)',
            1,    'rgba(239,68,68,0.75)',
          ],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'],
            5, 0.80,
            9, 0.0,
          ],
        },
      })
      map.addLayer({
        id: 'events-layer',
        type: 'circle',
        source: 'events',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 8, 7],
          'circle-color': severityColor(),
          'circle-opacity': 0.88,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#080a0e',
          'circle-stroke-opacity': 0.9,
        },
      })

      // ── Hotspot glow ring ───────────────────────────────────────────────
      map.addSource('hotspots', { type: 'geojson', data: toHotspotsGeoJSON(hotspotsRef.current) })
      map.addLayer({
        id: 'hotspots-glow',
        type: 'circle',
        source: 'hotspots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 18, 8, 32],
          'circle-color': 'transparent',
          'circle-opacity': 0,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': trendColor(),
          'circle-stroke-opacity': 0.4,
        },
      })

      // ── Hotspot center dot ──────────────────────────────────────────────
      map.addLayer({
        id: 'hotspots-layer',
        type: 'circle',
        source: 'hotspots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 8, 11],
          'circle-color': trendColor(),
          'circle-opacity': 0.92,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#080a0e',
        },
      })

      // ── Selection highlight ring ────────────────────────────────────────
      map.addSource('selected', { type: 'geojson', data: EMPTY_FC })
      map.addLayer({
        id: 'selected-ring',
        type: 'circle',
        source: 'selected',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 15, 8, 24],
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#4a9eff',
          'circle-stroke-opacity': 0.95,
        },
      })

      // ── Click handlers ──────────────────────────────────────────────────
      map.on('click', 'events-layer', (e) => {
        e.preventDefault()
        const id  = e.features[0].properties.id
        const evt = eventsRef.current.find(ev => ev.id === id)
        if (evt) onSelectRef.current({ type: 'event', data: evt })
      })

      map.on('click', 'hotspots-layer', (e) => {
        e.preventDefault()
        const id  = e.features[0].properties.id
        const hs  = hotspotsRef.current.find(h => h.id === id)
        if (hs) onSelectRef.current({ type: 'hotspot', data: hs })
      })

      // Pointer cursor on hover (desktop)
      for (const layer of ['events-layer', 'hotspots-layer', 'hotspots-glow']) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current  = null
      loadedRef.current = false
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync filtered events ─────────────────────────────────────────────────
  useEffect(() => {
    if (!loadedRef.current || !mapRef.current) return
    mapRef.current.getSource('events')?.setData(toEventsGeoJSON(events))
  }, [events])

  // ── Sync hotspots ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!loadedRef.current || !mapRef.current) return
    mapRef.current.getSource('hotspots')?.setData(toHotspotsGeoJSON(hotspots))
  }, [hotspots])

  // ── Sync layer visibility ─────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    const vis = (on) => on ? 'visible' : 'none'
    map.setLayoutProperty('heatmap-layer',  'visibility', vis(layersVisible.heatmap))
    map.setLayoutProperty('events-layer',   'visibility', vis(layersVisible.events))
    map.setLayoutProperty('hotspots-layer', 'visibility', vis(layersVisible.hotspots))
    map.setLayoutProperty('hotspots-glow',  'visibility', vis(layersVisible.hotspots))
  }, [layersVisible])

  // ── Sync selection: highlight ring + fly-to ──────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return

    if (!selectedItem) {
      map.getSource('selected')?.setData(EMPTY_FC)
      return
    }

    const { type, data } = selectedItem
    const coords = type === 'event'
      ? [data.longitude, data.latitude]
      : [data.centroid_lon, data.centroid_lat]

    map.getSource('selected')?.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: coords }, properties: {} }],
    })

    map.flyTo({
      center: coords,
      zoom: Math.max(map.getZoom(), 7),
      duration: 600,
      essential: true,
    })
  }, [selectedItem])

  return (
    <div className="map-panel">
      <div ref={containerRef} className="map-container" />
    </div>
  )
}
