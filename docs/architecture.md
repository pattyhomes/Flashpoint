# Architecture Reference

## Backend (`backend/app/`)

- **Entry:** `main.py` — FastAPI app, CORS middleware, router includes, startup/shutdown lifespan hooks (init DB, run migrations, start APScheduler)
- **Models:** `models.py` — `Event`, `Hotspot`, `IngestRun` (SQLAlchemy ORM → SQLite at `data/flashpoint.db`)
- **Schemas:** `schemas.py` — Pydantic request/response models; `EventOut`, `HotspotOut`, `HotspotDetailOut`, `SystemStatusOut`
- **Routes:** `routes/` — one file per resource: `health`, `events`, `hotspots`, `priorities`, `system`
- **Ingestion:** `services/ingestion/` — abstract `IngestionSource`, `MockSource` (dev), `GDELTSource` (real); normalizer + deduper
- **Scoring:** `services/scoring/` — DBSCAN clustering, confidence scoring, trend classification, proximity-weighted hotspot naming
- **Scheduler:** `jobs/scheduler.py` — APScheduler 30-min ingest cycle; failures logged to `IngestRun`
- **Migration pattern:** try/except ALTER TABLE in `main.py` `_migrate()` — additive only

## Frontend (`frontend/src/`)

- **State:** All data fetching and filter state lives in `App.jsx`. No external state library.
- **Filters:** `useMemo` chains — event type, severity threshold, confidence threshold, trend state. `eventTypeCounts` memo intentionally excludes `activeTypes` from deps so type toggles don't change displayed counts.
- **Components:** `Shell` (grid layout) → `FilterRail` (left), `MapPanel` (center, MapLibre GL), `PriorityList` + `DetailPane` (right), `EventFeed` (bottom), `StatusBar` (footer)
- **API client:** `services/api.js` — thin `fetch` wrapper for `/api/v1/*`
- **Styling:** CSS custom properties (`--text-muted`, `--font-mono`, `--sp-xs`, etc.) defined in `styles/index.css`; component styles in `styles/components.css`

## Desktop shell (`desktop/`)

- **Qt compat:** `desktop/app/qt_compat.py` — compatibility layer: tries PyQt6 first (Pi/system packages, supports RPi 5 16KB pages), then PySide6 (Mac/pip), then PyQt5 (legacy fallback, crashes on RPi 5). All shell code imports Qt symbols from here. `window.py` uses fully-qualified enum paths (`Qt.AlignmentFlag.*`, `Qt.WindowType.*`, `Qt.ContextMenuPolicy.*`) across all three bindings.
- **Config:** `desktop/app/config.py` — single source of truth for all desktop runtime constants (ports, timeouts, health poll settings, Pi seam flags). Both `launcher.py` and `window.py` import from here. Pi seam env vars: `FLASHPOINT_FULLSCREEN`, `FLASHPOINT_DEV_QUIT`, `FLASHPOINT_MANAGED`, `FLASHPOINT_PORTRAIT`.
- **Launcher:** `desktop/app/launcher.py` — orchestrates backend + frontend subprocesses, waits for readiness, then calls `desktop.app.main.main()` inline. Sets `FLASHPOINT_BACKEND_HEALTH_URL` and `FLASHPOINT_FRONTEND_URL` env vars before importing the shell. Managed ports: backend 8001, frontend 5178. `FLASHPOINT_MANAGED=1` skips subprocess management (Pi path).
- **Entry:** `desktop/app/main.py` — launched as `-m desktop.app.main` to avoid import collision with backend's `app/` package. Uses `config.FULLSCREEN` to call `showFullScreen()` vs `show()`.
- **Window:** `desktop/app/window.py` — `_HealthPoller` (QThread, polls health endpoint), `_OverlayWidget` (native connecting/unavailable state), `MainWindow` (state machine: CONNECTING → LOADING_WEBVIEW → READY | UNAVAILABLE). `BACKEND_HEALTH_URL` and `FRONTEND_URL` read from env vars (injected by launcher) with `config.STANDALONE_*` as fallbacks.
- **Mac Qt install:** `pip install -r desktop/requirements.txt` (PySide6 into existing `.venv`)
- **Pi Qt install:** `sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine` + `--system-site-packages` venv
