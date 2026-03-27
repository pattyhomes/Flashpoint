/**
 * parseUTC(iso)
 * Parse a naive UTC ISO string from the backend (no 'Z' suffix) as UTC.
 * Appends 'Z' if the string has no timezone designator. Guards against double-Z.
 * Returns null for falsy input.
 */
export function parseUTC(iso) {
  if (!iso) return null
  const s = String(iso)
  // Already has timezone info (Z, +, or - after the time component)
  if (/Z$|[+-]\d{2}:\d{2}$/.test(s)) return new Date(s)
  return new Date(s + 'Z')
}

/**
 * relativeTime(iso)
 * Human-readable age from an ISO string. Clamps negative diffs to 0 ("just now").
 * Format: "just now" | "Xs" | "Xm" | "Xh" | "Xd"
 * No "ago" suffix — matches EventFeed / DetailPane convention.
 */
export function relativeTime(iso) {
  if (!iso) return '—'
  const d = parseUTC(iso)
  if (!d) return '—'
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h`
  return `${Math.floor(hr / 24)}d`
}

/**
 * relativeTimeAgo(date)
 * Human-readable age from a Date object. Used by StatusBar.
 * Format: "just now" | "Xs ago" | "Xm ago" | "Xh ago" | "Xd ago"
 */
export function relativeTimeAgo(date) {
  if (!date) return null
  const sec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

/**
 * formatDate(iso)
 * Locale-formatted datetime from an ISO string, interpreted as UTC.
 * Example output: "Mar 27, 02:30 PM"
 */
export function formatDate(iso) {
  if (!iso) return '—'
  const d = parseUTC(iso)
  if (!d) return '—'
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
