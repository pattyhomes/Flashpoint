import { parseUTC, relativeTimeAgo } from '../../utils/time.js'

function stateLabel(systemStatus, lastPollFailed) {
  if (lastPollFailed) return 'SERVED FROM CACHE'
  if (!systemStatus) return 'BOOTING'
  if (systemStatus?.last_run_status === 'running') return 'INGEST SYNC'
  if (systemStatus?.last_run_status === 'failed') return 'INGEST FAILED'
  if (systemStatus?.is_stale) return 'STALE'
  return 'READY'
}

function TelemetryItem({ label, value, tone }) {
  return (
    <span className={`telemetry-item${tone ? ` telemetry-item--${tone}` : ''}`}>
      <span>{label}</span>
      <b>{value}</b>
    </span>
  )
}

export default function TelemetryBar({ systemStatus, lastUpdated, lastPollFailed, activeFilterCount }) {
  const successAt = parseUTC(systemStatus?.last_success_at)
  const generatedAt = parseUTC(systemStatus?.generated_at)
  const state = stateLabel(systemStatus, lastPollFailed)
  const stateTone = state.includes('FAILED') ? 'fail' : state.includes('STALE') || state.includes('CACHE') ? 'warn' : 'ok'

  return (
    <div className="telemetry-bar">
      <TelemetryItem label="UTC" value={(generatedAt || new Date()).toISOString().slice(11, 19)} />
      <TelemetryItem label="PIPELINE" value={state} tone={stateTone} />
      <TelemetryItem label="LAST GOOD" value={successAt ? relativeTimeAgo(successAt) : 'NONE'} />
      <TelemetryItem label="EVENTS" value={systemStatus?.event_count ?? 0} />
      <TelemetryItem label="HOTSPOTS" value={systemStatus?.hotspot_count ?? 0} />
      <TelemetryItem label="LEADS" value={systemStatus?.lead_count ?? 0} />
      <TelemetryItem label="SIGNALS" value={systemStatus?.mapped_signal_count ?? 0} />
      <TelemetryItem label="FILTERS" value={activeFilterCount} />
      <span className="telemetry-bar__updated">
        UI {lastUpdated ? relativeTimeAgo(lastUpdated) : 'BOOTING'}
      </span>
    </div>
  )
}
