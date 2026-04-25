# CLAUDE.md

## Context

Load `docs/prd/PRD_CONTEXT.md` at the start of any non-trivial session.
Consult full PDFs in `docs/prd/` when planning or resolving architectural ambiguity.

See @docs/architecture.md for backend/frontend/desktop component details.
See @docs/context.md for current state and next priorities.

## PRD Hierarchy

1. **Primary** — `docs/prd/PRD — Flashpoint Desktop for Raspberry Pi.pdf`
2. **Secondary** — `docs/prd/osintUnrestPRD.pdf` — product scope, UI principles, event model
3. **Technical reference** — `docs/prd/technicalPRD.pdf` — hardware, data model, performance targets

If PRDs conflict: Desktop PRD wins on architecture; osintUnrestPRD wins on product scope; technicalPRD wins on hardware/schema. Do not silently blend conflicting assumptions.

## Active Architecture

PySide6 desktop app (fullscreen) + QWebEngineView embedding React/Vite UI + FastAPI backend over localhost. This is the intentional transitional architecture.

Chromium kiosk mode is superseded. Do not plan or implement Chromium-based delivery.

## Development Commands

**Prerequisites:** Python 3.11+, Node.js 18+, repo venv at `.venv/`

### Desktop (all-in-one — preferred)
```bash
bash scripts/run.sh   # starts backend (8001), frontend (5178), PySide6 shell; Command+Q / Ctrl+Q to quit
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
bash scripts/dev_desktop.sh   # Command+Q / Ctrl+Q to quit
```

### Seed mock data
```bash
bash scripts/seed_mock_data.sh
```

### Backend tests
```bash
cd backend && ../.venv/bin/python -m pytest tests/ -v
# Single file: ../.venv/bin/python -m pytest tests/test_hotspot_naming.py -v
```

### Frontend lint
```bash
cd frontend && npm run lint
```
