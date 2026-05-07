# Architecture Reference

## Runtime Shape

Flashpoint is a transitional desktop appliance:

```text
PySide/PyQt shell
  -> QWebEngineView
    -> React/Vite/MapLibre frontend
      -> FastAPI localhost API
        -> SQLite
```

On the Pi, FastAPI serves the production frontend build from `frontend/dist/`.
`scripts/pi_start.sh` launches the shell in fullscreen managed mode against
`http://127.0.0.1:8000`.

## Backend

Entry:

- `backend/app/main.py` — FastAPI app, CORS, static frontend mount, router
  includes, startup/shutdown lifecycle, additive SQLite migrations, scheduler.

Data models:

- `Event` — confirmed/synthesized incident layer used by map, feed, hotspots.
- `EventSource` — provenance attached to confirmed events.
- `EvidenceItem` — raw source snapshot/provenance.
- `Observation` — candidate lead/context/linked/promoted intelligence.
- `Hotspot` — computed priority cluster.
- `IngestRun` — scheduler/source run history and freshness state.

Routes:

- `routes/health.py`
- `routes/events.py`
- `routes/hotspots.py` including `GET /api/v1/hotspots/{id}/trend`
- `routes/observations.py` including lead workflows and map signals
- `routes/priorities.py`
- `routes/system.py`

Ingestion:

- `services/ingestion/gdelt_source.py`
- `services/ingestion/event_registry_source.py`
- `services/ingestion/nws_source.py`
- `services/ingestion/bluesky_source.py`
- `services/ingestion/mastodon_source.py`
- `services/ingestion/acled_source.py`
- `jobs/seed.py` contains current ingestion job orchestration.
- `jobs/scheduler.py` registers enabled primary, supplementary, and observation
  source jobs.

Intelligence services:

- `services/intelligence.py` handles evidence insertion, observation insertion,
  map-signal eligibility, manual promote/dismiss/link, and safe auto-link/promote.
- `services/ai_embeddings.py` optionally calls Ollama and must fail soft.

Scoring:

- `services/scoring/hotspot.py` computes clusters, priorities, trend state, and
  hotspot naming.
- Hotspots must count only active confirmed/promoted events.

Migration pattern:

- Current migrations are additive `ALTER TABLE` guards in `backend/app/main.py`.
- Do not introduce destructive schema changes without an explicit migration plan.

## Frontend

Entry/state:

- `frontend/src/App.jsx` owns data fetching, polling, selection, filters, layer
  toggles, workspace state, and observation actions.
- `frontend/src/services/api.js` is the thin API wrapper.

Workstation layout:

- `components/layout/Shell.jsx`
- `components/layout/TopChrome.jsx`
- `components/layout/WorkspaceTabs.jsx`
- `components/layout/NavRail.jsx`
- `components/layout/ControlPopover.jsx`
- `components/layout/TelemetryBar.jsx`

Map:

- `components/map/MapPanel.jsx` owns MapLibre setup, dark basemap, confirmed heat,
  signal heat, clusters, dots, hotspot rings, and map gesture behavior.
- Overlay UI must stop map gestures from starting.

Right rail and incidents:

- `components/workstation/RightRail.jsx`
- `components/workstation/IncidentsDrawer.jsx`
- `components/priorities/PriorityList.jsx`
- `components/detail/DetailPane.jsx`
- `components/review/ObservationReview.jsx`

Styling:

- `frontend/src/styles/index.css` — design tokens and global rules.
- `frontend/src/styles/layout.css` — workstation grid and overlay placement.
- `frontend/src/styles/components.css` — component styling.
- Local fonts live in `frontend/public/fonts/`.

## Desktop Shell

- `desktop/app/qt_compat.py` tries PyQt6 first, then PySide6, then PyQt5.
  PyQt6 is required on Raspberry Pi 5 because PyQt5 crashes on 16KB pages.
- `desktop/app/config.py` centralizes runtime constants and env flags.
- `desktop/app/launcher.py` orchestrates backend/frontend subprocesses on Mac/dev.
- `desktop/app/main.py` starts the Qt application.
- `desktop/app/window.py` owns the native connecting/unavailable overlay and the
  QWebEngine window.

Important env flags:

- `FLASHPOINT_FULLSCREEN`
- `FLASHPOINT_DEV_QUIT`
- `FLASHPOINT_MANAGED`
- `FLASHPOINT_PORTRAIT`
- `FLASHPOINT_FRONTEND_URL`
- `FLASHPOINT_BACKEND_HEALTH_URL`

## Pi Runtime

Primary docs: `deploy/pi/README.md`.

Runtime checks:

```bash
ssh charlie@raspberrypi.local 'systemctl --user status flashpoint-backend.service --no-pager'
ssh charlie@raspberrypi.local 'systemctl --user status flashpoint-shell.service --no-pager'
ssh charlie@raspberrypi.local 'curl -fsS http://127.0.0.1:8000/api/v1/health'
```

When updating the Pi from Git:

```bash
ssh charlie@raspberrypi.local 'cd /home/charlie/projects/Flashpoint && git pull --ff-only'
ssh charlie@raspberrypi.local 'cd /home/charlie/projects/Flashpoint/frontend && npm run build'
ssh charlie@raspberrypi.local 'systemctl --user restart flashpoint-backend.service flashpoint-shell.service'
```
