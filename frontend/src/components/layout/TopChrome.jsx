import { formatDate } from '../../utils/time.js'

const WINDOWS = [
  { key: 6, label: '6H' },
  { key: 24, label: '24H' },
  { key: 72, label: '72H' },
  { key: 168, label: '7D' },
]

function healthLabel(status, lastPollFailed) {
  if (lastPollFailed) return { label: 'CACHE', tone: 'warn' }
  if (!status) return { label: 'BOOT', tone: 'sync' }
  if (status?.last_run_status === 'running') return { label: 'SYNC', tone: 'sync' }
  if (status?.last_run_status === 'failed') return { label: 'FAIL', tone: 'fail' }
  if (status?.is_stale) return { label: 'STALE', tone: 'warn' }
  return { label: 'READY', tone: 'ok' }
}

export default function TopChrome({
  systemStatus,
  lastPollFailed,
  timeWindow,
  onSetTimeWindow,
  openPopover,
  activePopover,
}) {
  const health = healthLabel(systemStatus, lastPollFailed)
  const generated = systemStatus?.generated_at ? new Date(systemStatus.generated_at) : new Date()

  return (
    <div className="top-chrome">
      <div className="brand-block">
        <span className="brand-mark">FP</span>
        <div className="brand-copy">
          <span className="brand-name">FLASHPOINT</span>
          <span className="brand-sub">LOCAL INTELLIGENCE WORKSTATION</span>
        </div>
      </div>

      <div className="top-controls" role="group" aria-label="Map controls">
        <div className="segmented" aria-label="Time window">
          {WINDOWS.map(item => (
            <button
              key={item.key}
              type="button"
              className={timeWindow === item.key ? 'is-active' : ''}
              onClick={() => onSetTimeWindow(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`chrome-button${activePopover === 'filters' ? ' is-active' : ''}`}
          onClick={() => openPopover(activePopover === 'filters' ? null : 'filters')}
        >
          FILTERS
        </button>
        <button
          type="button"
          className={`chrome-button${activePopover === 'layers' ? ' is-active' : ''}`}
          onClick={() => openPopover(activePopover === 'layers' ? null : 'layers')}
        >
          LAYERS
        </button>
      </div>

      <div className="top-readout">
        <span className="utc-readout">{formatDate(generated.toISOString())}</span>
        <span className={`health-pill health-pill--${health.tone}`}>
          <span className="health-pill__dot" />
          {health.label}
        </span>
      </div>
    </div>
  )
}
