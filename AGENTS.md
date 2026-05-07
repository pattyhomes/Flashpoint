# AGENTS.md

Flashpoint is a local-first unrest intelligence workstation for a Raspberry Pi
touch display. Keep this file short; load task-specific docs as needed.

## Always Read First

- For any non-trivial task: `docs/agent-handbook.md`
- For current priorities/status: `docs/context.md`
- For code structure: `docs/architecture.md`

## Task-Specific Docs

- Product or PRD ambiguity: `docs/prd/PRD_CONTEXT.md`, then the PDFs in `docs/prd/`
- Data/intelligence work: `docs/data-upgrade-plan.md`
- Pi runtime/deploy work: `deploy/pi/README.md`
- Desktop shell work: `desktop/README.md`
- V3 UI/design work: `docs/design/flashpoint-ui-v3/README.md`

## Non-Negotiables

- Active runtime is PySide/PyQt desktop shell + QWebEngine + FastAPI + SQLite.
- Chromium kiosk delivery is superseded; do not reintroduce browser kiosk plans.
- The Pi is a lightweight display appliance; do not put heavy AI runtime on it.
- Evidence/observations are provenance. Only confirmed/promoted `Event` rows affect
  hotspots and priority scoring.
- Keep touchscreen overlays from starting map gestures.
- Run the relevant verification commands before calling work complete.
