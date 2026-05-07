import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const STYLE = {
  version: 8,
  sources: {
    cartoDark: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    },
  },
  layers: [
    {
      id: 'carto-dark',
      type: 'raster',
      source: 'cartoDark',
      paint: {
        'raster-opacity': 0.86,
        'raster-brightness-max': 0.78,
        'raster-contrast': 0.08,
      },
    },
  ],
}
const US_CENTER = [-98, 38.5]
const US_ZOOM = 3.8
const EMPTY_FC = { type: 'FeatureCollection', features: [] }

function confirmedColor() {
  return ['step', ['get', 'severity_score'],
    '#5d8aa8', 0.4,
    '#ffb524', 0.6,
    '#ff7a18', 0.8,
    '#ff3a2e',
  ]
}

function hotspotColor() {
  return ['match', ['get', 'trend_state'],
    'escalating', '#ff5a3a',
    'declining', '#4ea36a',
    '#ffb524',
  ]
}

function toEventsGeoJSON(events) {
  return {
    type: 'FeatureCollection',
    features: events
      .filter(event => event.longitude != null && event.latitude != null)
      .map(event => ({
        type: 'Feature',
        id: event.id,
        geometry: { type: 'Point', coordinates: [event.longitude, event.latitude] },
        properties: {
          id: event.id,
          severity_score: event.severity_score,
          confidence_score: event.confidence_score,
          event_type: event.event_type,
        },
      })),
  }
}

function toSignalsGeoJSON(signals) {
  return {
    type: 'FeatureCollection',
    features: signals
      .filter(signal => signal.longitude != null && signal.latitude != null)
      .map(signal => ({
        type: 'Feature',
        id: signal.id,
        geometry: { type: 'Point', coordinates: [signal.longitude, signal.latitude] },
        properties: {
          id: signal.id,
          confidence_score: signal.confidence_score,
          severity_score: signal.severity_score,
          signal_weight: signal.signal_weight || 0.2,
          source_family: signal.source_family || 'signal',
        },
      })),
  }
}

function toHotspotsGeoJSON(hotspots) {
  return {
    type: 'FeatureCollection',
    features: hotspots
      .filter(hotspot => hotspot.centroid_lon != null && hotspot.centroid_lat != null)
      .map(hotspot => ({
        type: 'Feature',
        id: hotspot.id,
        geometry: { type: 'Point', coordinates: [hotspot.centroid_lon, hotspot.centroid_lat] },
        properties: {
          id: hotspot.id,
          trend_state: hotspot.trend_state || 'stable',
          priority_score: hotspot.priority_score || 0,
        },
      })),
  }
}

function mapLayerVisibility(map, id, visible) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
}

export default function MapPanel({
  events = [],
  hotspots = [],
  signals = [],
  selectedItem,
  onSelect,
  onSignalSelect,
  layersVisible = { events: true, hotspots: true, confirmedHeat: true, signalHeat: true },
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const loadedRef = useRef(false)
  const eventsRef = useRef(events)
  const hotspotsRef = useRef(hotspots)
  const signalsRef = useRef(signals)
  const onSelectRef = useRef(onSelect)
  const onSignalSelectRef = useRef(onSignalSelect)

  useEffect(() => { eventsRef.current = events }, [events])
  useEffect(() => { hotspotsRef.current = hotspots }, [hotspots])
  useEffect(() => { signalsRef.current = signals }, [signals])
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])
  useEffect(() => { onSignalSelectRef.current = onSignalSelect }, [onSignalSelect])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: US_CENTER,
      zoom: US_ZOOM,
      attributionControl: false,
      dragRotate: false,
      touchPitch: false,
    })

    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')

    map.on('load', () => {
      loadedRef.current = true

      map.addSource('events', { type: 'geojson', data: toEventsGeoJSON(eventsRef.current) })
      map.addSource('event-clusters', {
        type: 'geojson',
        data: toEventsGeoJSON(eventsRef.current),
        cluster: true,
        clusterRadius: 44,
        clusterMaxZoom: 7,
      })
      map.addSource('signals', { type: 'geojson', data: toSignalsGeoJSON(signalsRef.current) })
      map.addSource('signal-clusters', {
        type: 'geojson',
        data: toSignalsGeoJSON(signalsRef.current),
        cluster: true,
        clusterRadius: 52,
        clusterMaxZoom: 7,
      })
      map.addSource('hotspots', { type: 'geojson', data: toHotspotsGeoJSON(hotspotsRef.current) })
      map.addSource('selected', { type: 'geojson', data: EMPTY_FC })

      map.addLayer({
        id: 'confirmed-heat',
        type: 'heatmap',
        source: 'events',
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'severity_score'], 0, 0.4, 1, 1.8],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 28, 8, 48],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.9, 8, 2.2],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.85, 9, 0.05],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(0,0,0,0)',
            0.25, 'rgba(255,181,36,0.08)',
            0.48, 'rgba(255,122,24,0.32)',
            0.72, 'rgba(255,58,46,0.54)',
            1, 'rgba(255,58,46,0.78)',
          ],
        },
      })

      map.addLayer({
        id: 'signal-heat',
        type: 'heatmap',
        source: 'signals',
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'signal_weight'], 0, 0.25, 1, 1.4],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 24, 8, 42],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.65, 8, 1.6],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.62, 9, 0.1],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(0,0,0,0)',
            0.28, 'rgba(255,181,36,0.08)',
            0.55, 'rgba(255,181,36,0.30)',
            0.85, 'rgba(255,181,36,0.52)',
            1, 'rgba(255,181,36,0.68)',
          ],
        },
      })

      map.addLayer({
        id: 'signal-cluster-layer',
        type: 'circle',
        source: 'signal-clusters',
        filter: ['has', 'point_count'],
        paint: {
          'circle-radius': ['step', ['get', 'point_count'], 15, 8, 20, 30, 26],
          'circle-color': 'rgba(255,181,36,0.20)',
          'circle-stroke-color': '#ffb524',
          'circle-stroke-width': 1.2,
        },
      })
      map.addLayer({
        id: 'signal-cluster-count',
        type: 'symbol',
        source: 'signal-clusters',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 11,
        },
        paint: { 'text-color': '#ffcf6a' },
      })

      map.addLayer({
        id: 'event-cluster-layer',
        type: 'circle',
        source: 'event-clusters',
        filter: ['has', 'point_count'],
        paint: {
          'circle-radius': ['step', ['get', 'point_count'], 16, 8, 22, 30, 30],
          'circle-color': 'rgba(255,58,46,0.20)',
          'circle-stroke-color': '#ff5a3a',
          'circle-stroke-width': 1.4,
        },
      })
      map.addLayer({
        id: 'event-cluster-count',
        type: 'symbol',
        source: 'event-clusters',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 11,
        },
        paint: { 'text-color': '#ffe2dc' },
      })

      map.addLayer({
        id: 'signal-dots',
        type: 'circle',
        source: 'signal-clusters',
        filter: ['!', ['has', 'point_count']],
        minzoom: 6.5,
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 6.5, 4, 10, 7],
          'circle-color': '#ffb524',
          'circle-opacity': 0.72,
          'circle-stroke-color': '#080a0e',
          'circle-stroke-width': 1,
        },
      })

      map.addLayer({
        id: 'events-layer',
        type: 'circle',
        source: 'event-clusters',
        filter: ['!', ['has', 'point_count']],
        minzoom: 5.8,
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5.8, 5, 10, 9],
          'circle-color': confirmedColor(),
          'circle-opacity': 0.9,
          'circle-stroke-width': 1.2,
          'circle-stroke-color': '#05070b',
        },
      })

      map.addLayer({
        id: 'hotspots-glow',
        type: 'circle',
        source: 'hotspots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 19, 8, 38],
          'circle-color': 'transparent',
          'circle-stroke-width': ['interpolate', ['linear'], ['get', 'priority_score'], 0, 1, 1, 3],
          'circle-stroke-color': hotspotColor(),
          'circle-stroke-opacity': 0.5,
        },
      })
      map.addLayer({
        id: 'hotspots-layer',
        type: 'circle',
        source: 'hotspots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 8, 12],
          'circle-color': hotspotColor(),
          'circle-opacity': 0.95,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#05070b',
        },
      })

      map.addLayer({
        id: 'selected-ring',
        type: 'circle',
        source: 'selected',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 16, 8, 26],
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#6db3ff',
          'circle-stroke-opacity': 0.95,
        },
      })

      map.on('click', 'events-layer', (event) => {
        event.preventDefault()
        const id = event.features[0].properties.id
        const item = eventsRef.current.find(row => row.id === id)
        if (item) onSelectRef.current({ type: 'event', data: item })
      })

      map.on('click', 'hotspots-layer', (event) => {
        event.preventDefault()
        const id = event.features[0].properties.id
        const item = hotspotsRef.current.find(row => row.id === id)
        if (item) onSelectRef.current({ type: 'hotspot', data: item })
      })

      map.on('click', 'signal-dots', (event) => {
        event.preventDefault()
        const id = event.features[0].properties.id
        const signal = signalsRef.current.find(row => row.id === id)
        if (signal) onSignalSelectRef.current?.({ signal, lat: signal.latitude, lon: signal.longitude })
      })

      map.on('click', 'signal-cluster-layer', (event) => {
        event.preventDefault()
        const [lon, lat] = event.features[0].geometry.coordinates
        onSignalSelectRef.current?.({ lat, lon })
      })

      map.on('click', 'event-cluster-layer', (event) => {
        event.preventDefault()
        const coordinates = event.features[0].geometry.coordinates
        map.easeTo({ center: coordinates, zoom: Math.min(map.getZoom() + 1.5, 8.5), duration: 350 })
      })

      for (const layer of ['events-layer', 'hotspots-layer', 'signal-dots', 'signal-cluster-layer', 'event-cluster-layer']) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      loadedRef.current = false
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    map.getSource('events')?.setData(toEventsGeoJSON(events))
    map.getSource('event-clusters')?.setData(toEventsGeoJSON(events))
  }, [events])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    map.getSource('signals')?.setData(toSignalsGeoJSON(signals))
    map.getSource('signal-clusters')?.setData(toSignalsGeoJSON(signals))
  }, [signals])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    map.getSource('hotspots')?.setData(toHotspotsGeoJSON(hotspots))
  }, [hotspots])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    mapLayerVisibility(map, 'confirmed-heat', layersVisible.confirmedHeat)
    mapLayerVisibility(map, 'signal-heat', layersVisible.signalHeat)
    for (const id of ['events-layer', 'event-cluster-layer', 'event-cluster-count']) {
      mapLayerVisibility(map, id, layersVisible.events)
    }
    for (const id of ['signal-dots', 'signal-cluster-layer', 'signal-cluster-count']) {
      mapLayerVisibility(map, id, layersVisible.signalHeat)
    }
    for (const id of ['hotspots-layer', 'hotspots-glow']) {
      mapLayerVisibility(map, id, layersVisible.hotspots)
    }
  }, [layersVisible])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return

    if (!selectedItem) {
      map.getSource('selected')?.setData(EMPTY_FC)
      return
    }

    const coords = selectedItem.type === 'event'
      ? [selectedItem.data.longitude, selectedItem.data.latitude]
      : [selectedItem.data.centroid_lon, selectedItem.data.centroid_lat]

    map.getSource('selected')?.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: coords }, properties: {} }],
    })

    map.flyTo({ center: coords, zoom: Math.max(map.getZoom(), 7), duration: 600, essential: true })
  }, [selectedItem])

  return (
    <div className="map-panel">
      <div ref={containerRef} className="map-container" />
      <div className="map-hud" data-map-overlay>
        <span>LIVE MAP</span>
        <b>{events.length} CONFIRMED · {signals.length} SIGNALS · {hotspots.length} HOTSPOTS</b>
      </div>
      <div className="map-legend" data-map-overlay>
        <span><i className="legend-confirmed" />Confirmed</span>
        <span><i className="legend-signal" />Signal</span>
        <span><i className="legend-hotspot" />Priority</span>
      </div>
    </div>
  )
}
