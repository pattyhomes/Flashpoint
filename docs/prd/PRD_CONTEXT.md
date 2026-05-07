# Flashpoint PRD Context (Distilled)

Lightweight reference for implementation work. Consult the full PDFs in
`docs/prd/` for planning or architectural ambiguity.

## What Flashpoint Is

Flashpoint is a near-real-time U.S. unrest monitoring workstation: map-first,
source-backed, hotspot-aware, and local-first. It runs as a dedicated fullscreen
desktop application on a Raspberry Pi 5 touchscreen.

It should feel like installed field equipment, not a website.

Not in scope: generic news map, browser kiosk, fake military prop, surveillance
tool, people-level identification, accounts/collaboration, mobile app, or chat
assistant.

## Active Project Direction

The active runtime is:

```text
PySide/PyQt desktop shell
  -> QWebEngineView
    -> React/Vite/MapLibre UI
      -> FastAPI localhost backend
        -> SQLite
```

This is intentional transitional architecture. Do not collapse the transitional
web UI into native Qt prematurely. Preserve the real MapLibre map.

The active UI direction is the landscape V3 intelligence workstation. Historical
portrait-only PRD language is superseded for current implementation unless the
hardware/display direction is explicitly reopened.

## PRD Hierarchy

1. Primary architecture: `PRD — Flashpoint Desktop for Raspberry Pi.pdf`
2. Product scope, UI principles, event model: `osintUnrestPRD.pdf`
3. Hardware, schema, performance targets: `technicalPRD.pdf`

If PRDs conflict, apply the hierarchy above and record explicit overrides in
`docs/context.md`.

## Current Repo State (2026-05-07)

| Component | Status |
|---|---|
| FastAPI backend + SQLite | done |
| React/Vite frontend + MapLibre | done |
| PySide/PyQt desktop shell | done |
| Pi backend service + fullscreen shell runtime | done |
| V3 landscape workstation shell | done |
| Touch overlay/map gesture isolation | done |
| Evidence/Observation/Event provenance model | done |
| Observation APIs, map signals, source rail | done |
| Auto-link/auto-promote safety rules | initial implementation done |
| Stage 1.5 data quality upgrade | next planned data phase |

## Product Guardrails

- Touch-first and usable on the Pi display.
- Local-first; data stored and processed locally by default.
- Pi remains lightweight; do not run heavy AI on it.
- Dark, restrained, operational aesthetic.
- Truthful runtime state: freshness, stale, failed, syncing.
- No browser chrome in production.
- No Chromium kiosk delivery plan.
- Evidence and citations matter; provenance should be inspectable.
- Confirmed scoring must not be inflated by weak social/context records.

## Performance Targets

| Metric | Target |
|---|---|
| Cold boot -> usable dashboard | < 90 seconds |
| Native shell visible after session start | < 10 seconds |
| Dashboard initial load after shell | < 8 seconds |
| Map interaction latency | < 250 ms |
| Detail panel open | < 500 ms |
| 30-min ingest cycle | < 5 minutes |

## Explicitly Superseded

- Chromium kiosk mode as primary delivery.
- Launching `chromium-browser --kiosk` as the app.
- `deploy/flashpoint-kiosk.service`.
- Website-in-kiosk framing.
- Old portrait-only implementation direction for the current V3 workstation.

The technical PRD's hardware specs, data model concerns, performance targets,
and service-management requirements remain useful unless superseded above.

## Context Usage

| Use case | Load |
|---|---|
| Any non-trivial agent session | `AGENTS.md` or `CLAUDE.md`, then `docs/agent-handbook.md` |
| Current status and priorities | `docs/context.md` |
| Code structure | `docs/architecture.md` |
| Data/intelligence roadmap | `docs/data-upgrade-plan.md` |
| Product/architecture disputes | this file, then full PRD PDFs |
