# Flashpoint Agent Handbook

This is the persistent handoff for future Codex, Claude, or other coding-agent
sessions. Start here, then load the task-specific docs linked from `AGENTS.md`.

## Product Snapshot

Flashpoint is a local-first U.S. unrest monitoring workstation. It runs on a
Raspberry Pi 5 touchscreen as a fullscreen desktop appliance, with a real
MapLibre map, evidence-backed event provenance, hotspot priorities, and operator
status surfaces.

It is not a generic news map, a browser website in kiosk mode, a surveillance
tool, or a chat assistant.

## Active Architecture

- Runtime: PySide/PyQt desktop shell embeds React/Vite through QWebEngine.
- Backend: FastAPI over localhost, SQLite in `data/flashpoint.db`.
- Frontend: React + MapLibre, built by Vite and served by FastAPI on the Pi.
- Pi launch: user systemd backend service + transient shell service via
  `scripts/pi_start.sh`.
- Delivery direction: dedicated desktop appliance. Chromium kiosk mode is
  explicitly superseded.

## Current Product Direction

- Landscape V3 workstation is the active UI target.
- Preserve the real MapLibre map.
- Use the V3 operator shell: top chrome, workspace tabs, left nav rail, map-first
  center, right priority/source rail, Incidents drawer, bottom telemetry.
- Old portrait PRD language is historical unless a task explicitly reopens
  hardware orientation.
- Keep UI dense, touch-safe, and operational. Avoid marketing-page patterns.

## Intelligence Model

- `EvidenceItem` is raw provenance from sources.
- `Observation` is candidate intelligence extracted from evidence.
- `Event` is the confirmed/synthesized layer.
- `EventSource` records provenance linked to confirmed events.
- `Hotspot` and priority scoring must count only active confirmed/promoted events.
- Weak social/open-web observations may become amber map signals, but they must
  not create confirmed events or inflate hotspot scores by themselves.
- NWS/weather/context observations inform awareness only; they do not inflate
  unrest scoring.
- Corroboration requires independent source families. Syndicated copies are
  provenance, not confidence.

## PRD Hierarchy

1. Primary architecture: `docs/prd/PRD — Flashpoint Desktop for Raspberry Pi.pdf`
2. Product scope/UI principles/event model: `docs/prd/osintUnrestPRD.pdf`
3. Hardware/schema/performance targets: `docs/prd/technicalPRD.pdf`

If PRDs conflict, do not silently blend assumptions. Use the hierarchy above and
record any explicit override in `docs/context.md`.

## Development Commands

Prerequisites: Python 3.11+, Node.js 18+, repo venv at `.venv/`.

Desktop all-in-one:

```bash
bash scripts/run.sh
```

Backend only:

```bash
bash scripts/dev_backend.sh
```

Frontend only:

```bash
cd frontend && npm run dev
```

Shell only:

```bash
bash scripts/dev_desktop.sh
```

Seed mock data:

```bash
bash scripts/seed_mock_data.sh
```

## Verification

Run the smallest meaningful checks during development, and the full relevant
set before saying work is complete.

Backend:

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -v
```

Frontend:

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

Whitespace:

```bash
git diff --check
```

Pi health, when connected:

```bash
ssh charlie@raspberrypi.local 'cd /home/charlie/projects/Flashpoint && git status --short --branch'
ssh charlie@raspberrypi.local 'curl -fsS http://127.0.0.1:8000/api/v1/health'
ssh charlie@raspberrypi.local 'systemctl --user is-active flashpoint-backend.service; systemctl --user is-active flashpoint-shell.service'
```

Do not store credentials in repo docs. Use `raspberrypi.local` for the Pi when
available; old numeric school-network IPs may be stale.

## Repo Hygiene

- Prefer narrow, task-scoped edits.
- Do not rewrite full PRD PDFs.
- Use additive SQLite migrations in `backend/app/main.py` unless a proper
  migration system is introduced.
- Keep generated caches, screenshots, local DBs, and build outputs out of commits.
- Keep `AGENTS.md` and `CLAUDE.md` short. Put detailed context in docs and link
  to it.
