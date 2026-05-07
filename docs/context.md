# Project Context

Last updated: 2026-05-07

## Current State

| Component | Status |
|---|---|
| FastAPI backend | done |
| SQLite + additive migration style | done |
| React/Vite frontend | done |
| PySide/PyQt QWebEngine desktop shell | done |
| Pi systemd backend service + shell startup | done |
| Pi fullscreen kiosk behavior | done; close button hidden by default |
| V3 landscape workstation UI | active implementation direction |
| Real MapLibre map | preserved |
| Top chrome, workspace tabs, nav rail, right rail, Incidents drawer, telemetry | done |
| Touch overlay/map gesture isolation | done; preserve in future UI work |
| Event Registry ingestion | done; provenance, dedupe, confidence caps |
| Evidence/observation provenance layer | done |
| Observation APIs and map signals | done |
| Auto-link/auto-promote safety rules | initial implementation done |
| Stage 1.5 source health, local geocoder, local news/RSS | done |
| Hotspot trend endpoint | done |
| Local bundled fonts | done |

## Active Direction

The product direction is now a landscape V3 intelligence workstation for the Pi
display. Older portrait PRD wording is historical unless the hardware direction
is explicitly reopened.

The Pi is a display appliance. Heavy AI, Postgres/PostGIS, worker queues, richer
analyst workflows, and offline map tiles are future stages, not current runtime
requirements.

## Current Branch/Deployment

Recent work is on `codex/stage1-intelligence-upgrade`.

The Mac, GitHub branch, and Pi were aligned on this branch during the V3 pass.
If a future session starts elsewhere, check:

```bash
git status --short --branch
git fetch origin
git rev-list --left-right --count origin/main...HEAD
```

Pi repo path:

```bash
/home/charlie/projects/Flashpoint
```

Pi host:

```bash
raspberrypi.local
```

Do not record passwords in docs.

## Next Product Priority

Stage 1.5 is implemented as a SQLite-first data-quality pass. Next work should
focus on operationalizing real feeds and measuring quality:

1. Configure live `.env` source schedules for the Pi.
2. Expand the bundled U.S. gazetteer beyond the starter city/county dataset.
3. Add a small evaluation fixture set for auto-link/promote thresholds.
4. Tune exception categories and thresholds against real ingest runs.
5. Decide when source volume justifies Stage 2 Postgres/PostGIS + workers.

See `docs/data-upgrade-plan.md`.

## Known Design/Source Caveats

- Claude handoff URL for the V3 design returned `not found`; the gzipped original
  bundle could not be archived. The repo keeps the local fonts and design notes
  under `docs/design/flashpoint-ui-v3/`.
- Right rail priority detail was fixed after the V3 pass so expanded detail no
  longer clips and has pinned collapse controls.
