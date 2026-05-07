const BASE = '/api/v1'

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

// Returns EventPage: { items, total, limit, offset, has_more }
export const fetchEvents        = (limit = 500, offset = 0) => request(`/events/?limit=${limit}&offset=${offset}`)
// Returns EventDetailOut: EventOut + sources[]
export const fetchEventDetail   = (id)                      => request(`/events/${id}`)
export const fetchHotspots      = ()                        => request('/hotspots/')
export const fetchHotspotDetail = (id)                      => request(`/hotspots/${id}`)
export const fetchHotspotTrend  = (id, hours = 24)           => request(`/hotspots/${id}/trend?hours=${hours}`)
export const fetchPriorities    = ()                        => request('/priorities/')
export const fetchSystemStatus  = ()                        => request('/system/status')
export const fetchObservations  = (status = 'lead')          => request(`/observations/?status=${status}`)
export const fetchMapSignals    = ()                        => request('/observations/map-signals')
export const promoteObservation = (id)                       => request(`/observations/${id}/promote`, { method: 'POST' })
export const dismissObservation = (id)                       => request(`/observations/${id}/dismiss`, { method: 'POST' })
export const linkObservation    = (id, eventId)              => request(`/observations/${id}/link/${eventId}`, { method: 'POST' })
