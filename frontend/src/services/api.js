const BASE = '/api/v1'

async function request(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

// Returns EventPage: { items, total, limit, offset, has_more }
export const fetchEvents        = (limit = 500, offset = 0) => request(`/events/?limit=${limit}&offset=${offset}`)
export const fetchHotspots      = ()                        => request('/hotspots/')
export const fetchHotspotDetail = (id)                      => request(`/hotspots/${id}`)
export const fetchPriorities    = ()                        => request('/priorities/')
export const fetchSystemStatus  = ()                        => request('/system/status')
