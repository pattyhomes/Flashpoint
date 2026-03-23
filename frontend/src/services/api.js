const BASE = '/api/v1'

async function request(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

export const fetchEvents    = (limit = 100) => request(`/events/?limit=${limit}`)
export const fetchHotspots  = ()            => request('/hotspots/')
export const fetchPriorities = ()           => request('/priorities/')
