# Flashpoint UI Direction v3 Handoff

Source URL:
`https://api.anthropic.com/v1/design/h/NMK8hqk5QUGZCC1bBsSjuw?open_file=Flashpoint+UI+Direction+v3.html`

The handoff endpoint returned `not found` when re-fetched during implementation,
so the original gzipped bundle could not be archived in this pass. Implementation
uses the previously inspected v3 handoff details from the planning session.

Applied direction:
- Landscape 1280x720 workstation shell.
- PySide/QWebEngine app remains the kiosk path; no Chromium kiosk delivery.
- Real MapLibre map stays in the center.
- V3-inspired top chrome, tab bar, left nav rail, right priority/source rail,
  detail mode, map HUD, and bottom app-data telemetry.
- Local Inter, Inter Tight, and JetBrains Mono font files are stored in
  `frontend/public/fonts/`.
- Search, export, annotations, hardware CPU/NET/GPS telemetry, and offline map
  tiles are deferred.
