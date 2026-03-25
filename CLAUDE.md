# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

Load `docs/prd/PRD_CONTEXT.md` at the start of any non-trivial session.
Consult full PDFs in `docs/prd/` when planning or resolving architectural ambiguity.

## PRD Hierarchy

1. **Primary** — `docs/prd/PRD — Flashpoint Desktop for Raspberry Pi.pdf` — active source of truth
2. **Secondary** — `docs/prd/osintUnrestPRD.pdf` — product scope, UI principles, event model
3. **Technical reference** — `docs/prd/technicalPRD.pdf` — hardware, data model, performance targets

If PRDs conflict: Desktop PRD wins on architecture; osintUnrestPRD wins on product scope; technicalPRD wins on hardware/schema. Do not silently blend conflicting assumptions.

## Active Architecture

PySide6 desktop app (fullscreen) + QWebEngineView embedding the existing React/Vite UI + FastAPI backend over localhost. This is the intentional transitional architecture — not a permanent hack.

Chromium kiosk mode is superseded. Do not plan or implement Chromium-based delivery.

## Current State

| Component | Status |
|---|---|
| FastAPI backend | done |
| SQLite + models | done |
| React/Vite frontend | done |
| Events / hotspots / priorities APIs | done |
| Hotspot + trend computation | done |
| System status + freshness endpoint | done |
| Failure-aware operator status UI | done |
| Mock ingestion + IngestRun persistence | done |
| `desktop/` PySide6 shell (Milestone A) | done |
| Desktop runtime orchestration (launcher, managed ports) | done |
| Boot/autostart flow (Milestone B) | not started |
| Native shell surfaces (Milestone C) | not started |

## Next Priority

**Milestone B — Pi Runtime Integration:**
- Pi autostart (`~/.config/labwc/autostart` or equivalent)
- Systemd backend service
- Boot → operational flow tested on hardware
- Portrait/touch tuning, screen blanking control

---

## Development Commands

**Prerequisites:** Python 3.11+, Node.js 18+, repo venv at `.venv/`

### Desktop (all-in-one — preferred)
```bash
bash scripts/run.sh   # starts backend (8001), frontend (5178), PySide6 shell; Command+Q (macOS) / Ctrl+Q to quit
```

### Backend only (port 8000)
```bash
bash scripts/dev_backend.sh
# API docs: http://localhost:8000/docs
# Health: http://localhost:8000/api/v1/health
```

### Frontend only (Vite dev server, port 5173)
```bash
cd frontend && npm run dev
# Proxies /api → http://127.0.0.1:8000
```

### Shell only (requires backend + frontend on 8000/5173)
```bash
bash scripts/dev_desktop.sh   # Command+Q (macOS) / Ctrl+Q to quit
```

### Seed mock data
```bash
bash scripts/seed_mock_data.sh
```

### Backend tests
```bash
cd backend && ../.venv/bin/python -m pytest tests/ -v
# Run single test file:
../.venv/bin/python -m pytest tests/test_hotspot_naming.py -v
```

### Frontend lint
```bash
cd frontend && npm run lint
```

---

## Architecture Notes

### Backend (`backend/app/`)

- **Entry:** `main.py` — FastAPI app, CORS middleware, router includes, startup/shutdown lifespan hooks (init DB, run migrations, start APScheduler)
- **Models:** `models.py` — `Event`, `Hotspot`, `IngestRun` (SQLAlchemy ORM → SQLite at `data/flashpoint.db`)
- **Schemas:** `schemas.py` — Pydantic request/response models; `EventOut`, `HotspotOut`, `HotspotDetailOut`, `SystemStatusOut`
- **Routes:** `routes/` — one file per resource: `health`, `events`, `hotspots`, `priorities`, `system`
- **Ingestion:** `services/ingestion/` — abstract `IngestionSource`, `MockSource` (dev), `GDELTSource` (real); normalizer + deduper
- **Scoring:** `services/scoring/` — DBSCAN clustering, confidence scoring, trend classification, proximity-weighted hotspot naming
- **Scheduler:** `jobs/scheduler.py` — APScheduler 30-min ingest cycle; failures logged to `IngestRun`
- **Migration pattern:** try/except ALTER TABLE in `main.py` `_migrate()` — additive only

### Frontend (`frontend/src/`)

- **State:** All data fetching and filter state lives in `App.jsx`. No external state library.
- **Filters:** `useMemo` chains — event type, severity threshold, confidence threshold, trend state. `eventTypeCounts` memo intentionally excludes `activeTypes` from deps so type toggles don't change displayed counts.
- **Components:** `Shell` (grid layout) → `FilterRail` (left), `MapPanel` (center, MapLibre GL), `PriorityList` + `DetailPane` (right), `EventFeed` (bottom), `StatusBar` (footer)
- **API client:** `services/api.js` — thin `fetch` wrapper for `/api/v1/*`
- **Styling:** CSS custom properties (`--text-muted`, `--font-mono`, `--sp-xs`, etc.) defined in `styles/index.css`; component styles in `styles/components.css`

### Desktop shell (`desktop/`)

- **Launcher:** `desktop/app/launcher.py` — orchestrates backend + frontend subprocesses, waits for readiness, then calls `desktop.app.main.main()` inline. Sets `FLASHPOINT_BACKEND_HEALTH_URL` and `FLASHPOINT_FRONTEND_URL` env vars before importing the shell. Managed ports: backend 8001, frontend 5178. `FLASHPOINT_MANAGED=1` skips subprocess management (Pi path).
- **Entry:** `desktop/app/main.py` — launched as `-m desktop.app.main` to avoid import collision with backend's `app/` package
- **Window:** `desktop/app/window.py` — `_HealthPoller` (QThread, polls health endpoint), `_OverlayWidget` (native connecting/unavailable state), `MainWindow` (state machine: CONNECTING → LOADING_WEBVIEW → READY | UNAVAILABLE)
- **Config constants** (top of `window.py`): `BACKEND_HEALTH_URL` and `FRONTEND_URL` read from env with fallback to standalone defaults (8000/5173). `HEALTH_POLL_INTERVAL_MS`, `HEALTH_POLL_TIMEOUT_S`, `HEALTH_MAX_FAILURES` hardcoded.
- **Install PySide6:** `pip install -r desktop/requirements.txt` (into existing `.venv`)
