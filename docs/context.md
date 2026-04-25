# Project Context

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
| Event Registry ingestion source | done — classifier, dedupe, corroboration, confidence caps, source provenance |
| `event_sources` table + `EventDetailOut` API | done |
| `desktop/` PySide6 shell (Milestone A) | done |
| Desktop runtime orchestration (launcher, managed ports) | done |
| Desktop runtime configuration (`desktop/app/config.py`, Pi seam flags) | done |
| Pi backend service scaffolding (`deploy/pi/`, systemd user service) | done |
| Pi desktop autostart scaffolding (`deploy/pi/`, XDG autostart) | done |
| Pi frontend delivery (StaticFiles, `pi_start.sh` URL) | done — implemented, Mac-validated, not yet Pi hardware-validated |
| Pi end-to-end READY path | done — boot → READY confirmed on RPi 5 hardware |
| Boot/autostart flow (Milestone B) — hardware validation | done — PyQt6 required (PyQt5 crashes on RPi 5 16KB pages) |
| Native shell surfaces (Milestone C) | not started |

## Next Priority

**Milestone B is complete.** Remaining Pi polish (not blocking):
- Portrait/touch tuning, screen blanking control
- Auto-login setup (manual raspi-config step, documented in `deploy/pi/README.md`)

**Milestone C — Native shell surfaces** is the next active milestone.

**Frontend delivery:** Backend serves `frontend/dist/` via FastAPI `StaticFiles`.
`pi_start.sh` sets `FLASHPOINT_FRONTEND_URL=http://127.0.0.1:8000`. Build step required
on Pi before first boot — see `deploy/pi/README.md` Prerequisites.
