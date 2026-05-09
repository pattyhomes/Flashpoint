# Project Context

Last updated: 2026-05-09

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
| Stage 1.5 source health, Census geocoder, local news/RSS | done |
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

Recent work is merged to `main`.

The Mac, GitHub `main`, and Pi are aligned on the Stage 1.5 operational rollout.
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

Stage 1.5 is implemented as a SQLite-first data-quality pass. The operational
rollout enables NWS plus curated regional RSS first; Bluesky, Mastodon, and ACLED
stay disabled until credentials/access and noise expectations are confirmed.

Current operational artifacts:

1. `backend/app/data/rss_feed_registry.csv` stores the regional RSS pilot.
2. `scripts/generate_us_gazetteer.py` regenerates the Census-backed geocoder CSV.
3. `backend/tests/fixtures/stage15_eval_cases.json` stores the eval smoke set.
4. `scripts/run_observation_ingest.sh` runs a manual observation source ingest.
5. `scripts/report_source_quality.py` prints latest source run counts, rejection
   buckets, and bounded diagnostic samples.

Live data tuning now persists bounded source diagnostic samples on `IngestRun`
and exposes them through `/api/v1/sources/status`, the Sources rail, and
`scripts/report_source_quality.py`. These samples are operations metadata only;
they do not create events or affect hotspots.

The Sources rail now doubles as the Stage 1.5 source operations console: it
shows run history, quality samples, and Run Now controls for bounded observation
sources. Confirmed-source and hotspot rules remain unchanged.

Next work after rollout is threshold tuning against real ingest output, expanding
the eval fixture set with sampled false positives, and deciding whether source
volume justifies Stage 2 Postgres/PostGIS + workers.

2026-05-09 source tuning pass:

- Pi manual `nws` run fetched 252 active alerts and inserted 11 new context
  observations after dedupe.
- Pi manual `local_news` run with the Stage 1.5 rollout override fetched 32
  regional RSS items and rejected all 32 as `classified_out`; samples were
  ordinary civic/general news, so the broad pilot feeds remain enabled but
  annotated as healthy noisy feeds.
- The eval smoke fixture now includes sampled LAist false positives from that
  Pi run.
- Non-persisted Bluesky probe returned 403 from the public search endpoint; keep
  Bluesky disabled until authenticated access or adapter changes are available.
- Current volume does not justify Stage 2 Postgres/PostGIS + workers yet.

See `docs/data-upgrade-plan.md`.

## Known Design/Source Caveats

- Claude handoff URL for the V3 design returned `not found`; the gzipped original
  bundle could not be archived. The repo keeps the local fonts and design notes
  under `docs/design/flashpoint-ui-v3/`.
- Right rail priority detail was fixed after the V3 pass so expanded detail no
  longer clips and has pinned collapse controls.
