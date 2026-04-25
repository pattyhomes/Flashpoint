# Flashpoint — PRD Context (Distilled)

Lightweight reference for daily implementation work.
Load alongside CLAUDE.md. Consult full PDFs for planning or architectural decisions.

---

## What Flashpoint Is

A near-real-time U.S. unrest monitoring workstation — map-first, source-backed, hotspot-aware.
Runs as a **dedicated desktop application** on a Raspberry Pi 5 touchscreen.
Feels like a real piece of installed equipment, not a website.

**Not:** a generic news map, a browser kiosk, a fake military prop, a surveillance product, a chat assistant.

---

## Active Project Direction

**PySide6 desktop application shell** embedding the existing React/MapLibre frontend via QWebEngineView, talking to the FastAPI backend over localhost.

This is the **intentional transitional architecture** — not a permanent hack, not a final product. The transition is: wrap and control what already works, then progressively own more of the application experience natively.

---

## Architecture (Near-Term)

```
PySide6 Desktop App (fullscreen, no browser chrome)
├── QWebEngineView  ←  existing React/Vite UI (map, feed, priorities)
├── native: loading screen, backend-unavailable state, retry
└── talks to FastAPI backend via localhost:8000

FastAPI Backend
├── /api/v1/events, /hotspots, /priorities, /system/status
├── APScheduler (30-min ingest cycle)
└── SQLite  ←  data/flashpoint.db
```

---

## Temporary vs Permanent Strategy

| Layer | Temporary (now) | Permanent (direction) |
|---|---|---|
| Frontend | React/Vite embedded in QWebEngineView | selected surfaces → native Qt widgets |
| Map | MapLibre in web view | may stay web-rendered (best fit) |
| Backend | FastAPI as separate local service | packaged as product runtime |
| Shell | PySide6 wraps existing UI | native shell owns lifecycle, status, settings |
| Boot | systemd backend + desktop autostart entry | desktop app supervises own runtime |

**Do not collapse temporary → permanent prematurely.** Mark transitional code clearly.

---

## Current Repo State (2026-03-24)

| Component | Status |
|---|---|
| FastAPI backend | done |
| SQLite + models | done |
| React/Vite frontend | done |
| MapLibre map panel | done |
| Events / hotspots / priorities APIs | done |
| Hotspot + trend computation | done |
| System status + freshness endpoint | done |
| IngestRun persistence | done |
| Failure-aware operator status UI | done |
| Mock data ingestion | done |
| `desktop/` PySide6 shell (Milestone A) | **done** |
| Boot/autostart flow (Milestone B) | **not started** |
| Native shell surfaces (Milestone C) | **not started** |

---

## Top Engineering Priorities

1. ~~**Milestone A — Desktop Shell Bootstrap** — COMPLETE~~
   - `desktop/` scaffold, PySide6 fullscreen app, QWebEngineView, native loading/unavailable states

2. **Milestone B — Pi Runtime Integration**
   - Pi autostart (desktop session `~/.config/labwc/autostart` or equivalent)
   - Systemd backend service
   - Boot → operational flow tested
   - Portrait/touch tuning, screen blanking control

3. **Milestone C — Native Operator Shell**
   - Native startup screen
   - Native runtime state / status ribbon
   - Tighter connection/recovery lifecycle

---

## Product Guardrails

- Touch-first: works on Pi Touch Display 2, portrait 720×1280, no hover-only interactions
- Local-first: all data stored and processed locally, no cloud required
- Dark, restrained, tactical aesthetic — not theatrical, not cluttered
- Truthful operational state: freshness, stale, failed, syncing — communicated clearly
- No browser chrome visible in production
- No accounts, no collaboration, no mobile app, no global coverage
- No AI HAT required (Pi 5 CPU only for V1)
- Not a surveillance product, not people-level identification

---

## Performance Targets (from technicalPRD)

| Metric | Target |
|---|---|
| Cold boot → usable dashboard | < 90 seconds |
| Native shell visible after session start | < 10 seconds |
| Dashboard initial load after shell | < 8 seconds |
| Map interaction latency | < 250 ms |
| Detail panel open | < 500 ms |
| 30-min ingest cycle | < 5 minutes |

---

## Hardware Target

- Board: Raspberry Pi 5
- Display: Raspberry Pi Touch Display 2 (7-inch, 720×1280, portrait, touch)
- OS: Raspberry Pi OS 64-bit with desktop
- Storage: 64GB microSD
- Power: 5V/5A USB-C
- Cooling: active
- AI HAT: **not required**

---

## Explicitly Superseded

- Chromium kiosk mode as primary delivery
- Any plan to launch `chromium-browser --kiosk` as the application
- `deploy/flashpoint-kiosk.service` (Chromium-based)
- "Website in kiosk mode" framing
- V1 technical PRD's preference for Chromium kiosk (replaced by Desktop PRD architecture decision)

> The technical PRD's hardware specs, data model, performance targets, and service management requirements remain binding. Only the delivery-form sections are superseded.

---

## Context Usage Guide

| Use case | What to load |
|---|---|
| Day-to-day implementation | CLAUDE.md + this file |
| Planning a new milestone | + Desktop PRD (§12–32) |
| Product scope / feature questions | + osintUnrestPRD |
| Schema / hardware / performance | + technicalPRD |
| Architectural conflicts or ambiguity | all three PDFs |
