<div align="center">

<img src="frontend/public/favicon.svg" width="64" height="64" alt="Flashpoint" />

# Flashpoint

**Local-first U.S. civil unrest monitoring workstation**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=black)](https://react.dev)
[![MapLibre GL](https://img.shields.io/badge/MapLibre_GL-5.21-396CB2)](https://maplibre.org)
[![SQLite](https://img.shields.io/badge/SQLite-3-003b57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi-5-c51a4a?logo=raspberry-pi&logoColor=white)](https://raspberrypi.com)
[![Tests](https://img.shields.io/badge/tests-160_passing-22c55e)](backend/tests/)

</div>

---

Flashpoint is a single-operator U.S. unrest and disruption monitoring workstation that aggregates, classifies, deduplicates, and visualizes U.S. protest and civil disruption events on a near-real-time 30-minute ingest cycle with last-known-data fallback. It runs as a fullscreen native desktop application — designed to live permanently on a **Raspberry Pi 5 with a 7-inch touchscreen**, feeling like a real piece of installed equipment rather than a website.

The pipeline pulls from public OSINT sources (GDELT 2.0, Event Registry), runs each article through a **deterministic NLP classifier**, deduplicates across sources with a **6-rule syndication detector**, builds **multi-source corroborated confidence scores**, clusters events into geographic hotspots with **greedy radius clustering and proximity-weighted naming**, and serves everything through a **FastAPI backend + React/MapLibre GL dashboard**, embedded in a PySide6/PyQt6 Qt shell with zero browser chrome.

<!-- SCREENSHOT: Add a screenshot of the running dashboard here.
     Suggested: `docs/screenshot.png` — capture the map with hotspot markers,
     the priority list, and the status bar. Then uncomment the line below.
-->
<!-- ![Flashpoint dashboard screenshot](docs/screenshot.png) -->

---

## Features

- **Multi-source ingestion** — GDELT 2.0 (free, 15-min cadence), Event Registry (API key, supplementary), NWS context, Bluesky/Mastodon weak signals, optional ACLED, and configured Local News/RSS feeds. Mock source for dev and demo.
- **Deterministic classifier** — four-signal NLP pipeline (title keywords, body keywords, DMOZ categories, Wikipedia concepts). No LLM, no external calls. Classifies into 8 event types: `protest`, `riot`, `political_violence`, `police_clash`, `vandalism_tied_to_unrest`, `crowd_disruption`, `protest_related_road_shutdown`, `unrest`.
- **Three-layer deduplication** — exact `source_id` match → cross-source similarity (haversine + time window + Jaccard title) → syndicated copy detection (6 rules: same outlet, wire family, title similarity, wire domain URL, timestamp proximity, ER event URI grouping).
- **Evidence-first intelligence model** — raw sources create `EvidenceItem` and `Observation` records first. Safe independent-family corroboration can auto-link/promote; weak social volume remains signal heat until corroborated.
- **Stage 1.5 data-quality controls** — observation location confidence/reasons, exception categories, source run stats, source health API, a Census-backed U.S. city/county gazetteer, and a curated RSS registry keep bad geography and noisy sources out of hotspots.
- **Corroboration model** — each independent source family can add confidence. Syndicated wire republications (AP, Reuters, UPI, AFP, CNN, NBC) add zero. Uncorroborated ER-only events are confidence-capped by location precision tier (venue: 0.62, city: 0.58, state: 0.45).
- **Geographic hotspot clustering** — two-pass greedy radius algorithm (75-mile metro radius, 72-hour event window). City/venue events anchor and merge in pass 1; state-level signals fall back to pass 2 state grouping. Pruned to minimum 3 events, capped at 15 hotspots.
- **Proximity-weighted hotspot naming** — ranks candidate city names by `count / (1 + mean_distance / 50mi)` so the closest, most-frequent city wins. Falls back to county → state region → coordinates.
- **Trend analysis** — compares 0–8h vs 8–24h event windows per cluster. Escalating / stable / declining with severity delta gating.
- **V3 workstation UI** — landscape, map-first operator shell with top chrome, real workspace tabs, left navigation rail, right priority/source rail, Incidents drawer, local fonts, and app-data telemetry.
- **Confirmed + signal map layers** — MapLibre GL with local in-code CARTO dark raster style. Confirmed events render as red/orange heat, clusters, and dots; eligible unconfirmed observations render as separate amber signal heat.
- **60-second polling with selection reconciliation** — hotspots, priorities, and system status refresh automatically. If the selected hotspot is recomputed away (ID reuse), the selection is transparently cleared.
- **Operator status surface** — status bar shows data freshness, staleness detection, run-failed alerts, and ingest-cycle sync indicators.
- **Touch-ready Pi appliance** — systemd user service + XDG autostart + fullscreen Qt shell with native connecting/unavailable overlay states. No browser chrome, no accounts, no cloud.
- **160 backend tests** — classifier, deduplication, corroboration, confidence model, clustering, hotspot naming, evidence workflows, source health, geocoding, RSS registry, eval smoke fixtures, map signals, and hotspot trend buckets.

---

## Architecture

```mermaid
graph TD
    subgraph Sources
        G[GDELT 2.0<br/>15-min CSVs]
        ER[Event Registry<br/>API]
        OBS[NWS / Social / RSS<br/>observations]
        M[Mock Source<br/>dev/demo]
    end

    subgraph "Backend — FastAPI + APScheduler"
        CL[Deterministic<br/>Classifier]
        GEO[Local Geocoder<br/>confidence + reason]
        DD[3-Layer<br/>Deduplicator]
        CB[Corroboration<br/>Engine]
        DB[(SQLite<br/>flashpoint.db)]
        HS[Hotspot<br/>Clustering]
        API[REST API<br/>/api/v1/...]
        SF[Static Files<br/>frontend/dist/]
    end

    subgraph "Frontend — React + MapLibre GL"
        MAP[Map Panel<br/>MapLibre GL]
        FIL[Filter Rail]
        PRI[Priority List]
        DET[Detail Pane]
        FEED[Event Feed]
        SB[Status Bar]
    end

    subgraph "Desktop Shell — PySide6 / PyQt6"
        QW[QWebEngineView]
        HP[Health Poller<br/>QThread]
        OV[Native Overlay<br/>CONNECTING → READY]
    end

    G --> CL
    ER --> CL
    OBS --> CL
    CL --> GEO
    M --> DD
    GEO --> DD
    DD --> CB
    CB --> DB
    DB --> HS
    HS --> DB
    DB --> API
    API --> MAP
    API --> PRI
    API --> FEED
    SF --> QW
    QW --> MAP
    HP --> OV
    API -.->|health poll| HP
```

### Deployment topology (Raspberry Pi)

```
Pi boots → auto-login (pi user)
  │
  ├── systemd --user → flashpoint-backend.service
  │     └── uvicorn app.main:app  (127.0.0.1:8000)
  │           └── serves frontend/dist/ as static files
  │
  └── XDG autostart → pi_start.sh → python -m desktop.app.main
        └── PySide6 / PyQt6 fullscreen window
              ├── QWebEngineView  →  http://127.0.0.1:8000
              └── HealthPoller (QThread, polls /api/v1/health)
                    CONNECTING → LOADING_WEBVIEW → READY
```

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Backend** | Python 3.11+, FastAPI 0.111+ | ASGI via uvicorn |
| **ORM / DB** | SQLAlchemy 2.0, SQLite | 4 tables: events, hotspots, event_sources, ingest_runs |
| **Scheduling** | APScheduler 3.10 | Background ingest cycles (30-min default) |
| **HTTP client** | httpx 0.27 | GDELT CSV fetches, Event Registry API calls |
| **Config** | pydantic-settings 2.0 | `.env`-backed, typed settings |
| **Frontend** | React 19, Vite 8 | No external state library |
| **Map** | MapLibre GL 5.21 | CARTO Dark Matter basemap |
| **Desktop (Mac)** | PySide6 6.6+ | pip-installed |
| **Desktop (Pi)** | PyQt6 (system packages) | `python3-pyqt6.qtwebengine` via apt — PyQt5 crashes on RPi 5 16KB pages (commit 33e08b9) |
| **Qt compat layer** | `desktop/app/qt_compat.py` | Tries PyQt6, then PySide6, then PyQt5 (legacy fallback) |
| **Pi OS** | Raspberry Pi OS 64-bit Bookworm | systemd user service + XDG autostart |
| **Testing** | pytest | 160 tests, zero external calls |

---

## Quick Start

**Prerequisites:** Python 3.11+, Node.js 18+

```bash
# 1. Clone and set up the Python environment
git clone https://github.com/pattyhomes/Flashpoint.git
cd Flashpoint
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Configure environment
cp .env.example .env
# Edit .env if needed — defaults use mock data, no API keys required

# 4. Install desktop shell (Mac)
pip install -r desktop/requirements.txt

# 5. Seed mock data and launch everything
bash scripts/seed_mock_data.sh
bash scripts/run.sh
```

`scripts/run.sh` starts the backend (port 8001), frontend dev server (port 5178), and the PySide6 desktop shell in a single command. Press `Command+Q` (macOS) to quit.

For a fullscreen kiosk-style dev run with no window chrome, use the Qt shell kiosk launcher:

```bash
bash scripts/run_kiosk.sh
```

This uses the same backend/frontend orchestration as `scripts/run.sh`, but exports
`FLASHPOINT_FULLSCREEN=1`. The Raspberry Pi autostart path already uses the same
fullscreen shell mode through `scripts/pi_start.sh`.

On the Pi, `scripts/pi_start.sh` hides the native close button by default for kiosk
use. For maintenance sessions, launch with `FLASHPOINT_DEV_QUIT=1` to show the
close affordance and enable the shell quit shortcut.

### Individual services

```bash
# Backend only (port 8000, with hot reload)
bash scripts/dev_backend.sh
# → API docs:    http://localhost:8000/docs
# → Health:      http://localhost:8000/api/v1/health

# Frontend only (Vite dev server, port 5173)
cd frontend && npm run dev
# → Proxies /api → http://127.0.0.1:8000

# Desktop shell only (requires backend + frontend already running)
bash scripts/dev_desktop.sh
```

---

<details>
<summary><strong>Project Structure</strong></summary>

```
Flashpoint/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, CORS, static files
│   │   ├── config.py                # pydantic-settings (all env vars)
│   │   ├── models.py                # Event, Hotspot, EventSource, IngestRun
│   │   ├── schemas.py               # Pydantic request/response models
│   │   ├── routes/                  # health, events, hotspots, priorities, sources, system
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   │   ├── gdelt_source.py          # GDELT 2.0 CSV ingestion
│   │   │   │   ├── eventregistry_source.py  # Event Registry API
│   │   │   │   ├── local_news_source.py     # RSS/Atom + allowlisted article fetches
│   │   │   │   ├── rss_registry.py          # Curated regional/news feed registry
│   │   │   │   ├── mock_source.py           # Dev/demo data
│   │   │   │   ├── classifier.py            # Deterministic NLP classifier
│   │   │   │   ├── deduper.py               # 3-layer deduplication
│   │   │   │   └── normalizer.py
│   │   │   └── scoring/
│   │   │       └── hotspot.py               # Clustering, scoring, trend, naming
│   │   └── jobs/
│   │       ├── scheduler.py         # APScheduler job registration
│   │       └── seed.py              # Ingestion runners + mock seeding
│   └── tests/
│       ├── test_classifier.py
│       ├── test_deduper_enhanced.py
│       ├── test_eventregistry_confidence.py
│       ├── test_eventregistry_ingestion.py
│       ├── test_hotspot_clustering.py
│       └── test_hotspot_naming.py
│
├── frontend/
│   └── src/
│       ├── App.jsx                  # Root — all state, polling, filtering
│       ├── components/
│       │   ├── layout/              # V3 chrome, tabs, nav rail, telemetry
│       │   ├── map/                 # MapPanel (MapLibre GL)
│       │   ├── priorities/          # PriorityList
│       │   ├── detail/              # DetailPane
│       │   ├── review/              # Sources/Leads exception review
│       │   ├── workstation/         # RightRail, IncidentsDrawer
│       │   └── feed/                # EventFeed rows reused in drawer
│       ├── services/api.js          # Fetch wrapper for /api/v1/*
│       └── styles/                  # CSS custom properties, dark theme
│
├── desktop/
│   └── app/
│       ├── qt_compat.py             # PyQt6/PySide6/PyQt5 compatibility layer
│       ├── config.py                # Runtime constants (ports, timeouts, Pi flags)
│       ├── launcher.py              # Subprocess orchestrator (dev path)
│       ├── main.py                  # Entry point: python -m desktop.app.main
│       └── window.py                # MainWindow, HealthPoller, OverlayWidget
│
├── deploy/pi/
│   ├── install.sh                   # Installs systemd service + XDG autostart
│   ├── flashpoint-backend.service   # systemd user service template
│   └── flashpoint.desktop           # XDG autostart entry template
│
├── scripts/
│   ├── run.sh                       # All-in-one dev launcher (preferred)
│   ├── dev_backend.sh
│   ├── dev_desktop.sh
│   ├── seed_mock_data.sh
│   └── pi_start.sh                  # Pi shell launcher
│
└── data/
    └── flashpoint.db                # SQLite (gitignored)
```

</details>

---

## Data Pipeline

```mermaid
flowchart LR
    subgraph Ingest
        G[GDELT CSV\n15-min windows]
        ER[Event Registry\nArticle API]
    end

    subgraph Classify
        CL{Deterministic\nClassifier\n4-signal pipeline}
        PASS[event_type\n+ score ≥ 0.6]
        FAIL[Discard]
        CL --> PASS
        CL --> FAIL
    end

    subgraph Deduplicate
        L1[Layer 1\nExact source_id]
        L2[Layer 2\nLocation + time\n+ Jaccard title]
        L3[Layer 3\nSyndication detect\n6 rules]
    end

    subgraph Store
        DB[(SQLite\nevents\nhotspots\nevent_sources\ningest_runs)]
    end

    subgraph Cluster ["Cluster & Score  (every ingest cycle)"]
        P1[Pass 1\nCity/venue events\n75-mile radius merge]
        P2[Pass 2\nState-level fallback\ngroup by state]
        SC[Score\nseverity · confidence\nmomentum · priority]
        TR[Trend\n0–8h vs 8–24h\nescalating / stable / declining]
        NM[Name\nproximity-weighted\ncity ranking]
    end

    subgraph Serve
        API[FastAPI\nREST endpoints]
        UI[React + MapLibre GL]
    end

    G --> L1
    ER --> CL
    PASS --> L1
    L1 -->|new| L2
    L2 -->|cross-source match| L3
    L3 -->|independent +0.08 conf| DB
    L3 -->|syndicated weight=0| DB
    L2 -->|no match + discovery on| DB
    DB --> P1
    P1 --> P2
    P2 --> SC
    SC --> TR
    TR --> NM
    NM --> DB
    DB --> API
    API --> UI
```

**Key design decisions:**
- GDELT events start at confidence 0.50 (single source); each additional GDELT article referencing the same event adds +0.10
- ER events start conservative (0.30–0.62) and are capped until independently corroborated
- Wire service families (AP, Reuters, UPI, AFP, CNN, NBC) are tracked so syndicated republications don't inflate source counts
- State-level location signals are allowed to contribute to clusters but don't shift city-level centroids

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Service health + DB connectivity |
| `GET` | `/api/v1/events/` | Paginated event list (default limit 500, max 1000) |
| `GET` | `/api/v1/events/{id}` | Event detail with full source provenance |
| `GET` | `/api/v1/hotspots/` | All hotspots ordered by priority score |
| `GET` | `/api/v1/hotspots/{id}` | Hotspot detail with member events |
| `GET` | `/api/v1/priorities/` | Top 3 hotspots (quick dashboard summary) |
| `GET` | `/api/v1/system/status` | Freshness, staleness, run status, counts |

Interactive API docs available at `http://localhost:8000/docs` when the backend is running.

---

<details>
<summary><strong>Configuration (.env reference)</strong></summary>

```bash
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000

DATABASE_URL=sqlite:///./data/flashpoint.db

# Primary ingestion source: "mock" (dev) or "gdelt" (production)
INGEST_SOURCE=mock
MOCK_DATA_ENABLED=true
INGESTION_INTERVAL_SECONDS=1800    # 30 minutes

# Event Registry — supplementary source (runs alongside GDELT/mock)
# EVENT_REGISTRY_ENABLED=false
# EVENT_REGISTRY_API_KEY=                          # required when enabled
# EVENT_REGISTRY_INTERVAL_SECONDS=1800
# EVENT_REGISTRY_LOOKBACK_HOURS=6
# EVENT_REGISTRY_MAX_RECORDS=100
# EVENT_REGISTRY_MIN_CLASSIFICATION_SCORE=0.6
# EVENT_REGISTRY_MIN_LOCATION_PRECISION=city       # venue | city | state
# EVENT_REGISTRY_CREATE_NEW_EVENTS=false           # enable novel event discovery
# EVENT_REGISTRY_MAX_NEW_EVENTS_PER_RUN=10
# EVENT_REGISTRY_MAX_CONFIDENCE_UNCORROBORATED=0.58

# Stage 1.5 observation sources
# NWS_ALERTS_ENABLED=false
# NWS_ALERTS_AREA=                              # empty = national active alerts
# LOCAL_NEWS_ENABLED=false
# LOCAL_NEWS_FEED_URLS=                         # empty uses backend/app/data/rss_feed_registry.csv
# LOCAL_NEWS_ALLOWED_DOMAINS=                   # required only when overriding feed URLs
# LOCAL_NEWS_FETCH_ARTICLES=true
#
# First Pi rollout enables NWS + regional RSS only.
# Bluesky, Mastodon, and ACLED remain disabled until credentials/access are confirmed.

# Desktop shell (Pi deployment overrides)
# FLASHPOINT_FULLSCREEN=1
# FLASHPOINT_MANAGED=1    # skip subprocess management (systemd handles services)
# FLASHPOINT_DEV_QUIT=0
```

</details>

---

## Testing

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -v
```

160 tests across the backend suite — all run in-process against in-memory SQLite, zero external API calls:

| File | Coverage |
|---|---|
| `test_classifier.py` | Keyword/phrase patterns, multi-signal reinforcement, hard exclusion rules, type mappings, downgrade logic |
| `test_deduper_enhanced.py` | All 6 syndication rules, cross-source similarity matching, best-match scoring |
| `test_eventregistry_confidence.py` | Initial confidence formula, precision-tier caps, corroboration uplift arithmetic |
| `test_eventregistry_ingestion.py` | Discovery gating, confidence capping, source_count integrity, IngestRun tracking |
| `test_hotspot_clustering.py` | Cluster radius merge/separation, centroid stability, MIN_EVENTS pruning, trend classification, momentum decay |
| `test_hotspot_naming.py` | Proximity-weighted ranking, state/country exclusion, county fallback, coordinate fallback |
| `test_stage15_data_upgrade.py` | Evidence/observation source stats, location gates, source status, local news ingestion |
| `test_stage15_operational_rollout.py` | RSS registry, Census-backed geocoder, eval smoke report, manual ingest helper |

```bash
# Lint frontend
cd frontend && npm run lint
```

Source quality report:

```bash
./scripts/report_source_quality.py
```

The report prints latest source run counts, rejection buckets, and bounded sample records for tuning RSS/news feeds without opening the Pi UI.

The Sources rail also includes recent run history and Run Now controls for bounded observation sources (`nws`, `local_news`, and future configured weak-signal sources).

---

<details>
<summary><strong>Raspberry Pi Deployment</strong></summary>

### Hardware

| Component | Spec |
|---|---|
| Board | Raspberry Pi 5 (8GB recommended) |
| Display | Pi Touch Display 2 — 7-inch, 720×1280, portrait, capacitive touch |
| Storage | 64GB microSD (A2 class) |
| Power | 5V/5A USB-C |
| Cooling | Active cooling recommended |

### Prerequisites

```bash
# On the Pi (Raspberry Pi OS 64-bit Bookworm with desktop)
sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine
sudo apt install nodejs npm    # or use nvm

# Clone the repo and set up
git clone https://github.com/pattyhomes/Flashpoint.git ~/Flashpoint
cd ~/Flashpoint

# Create venv with system-site-packages (required for system PyQt6;
# PyQt5 crashes on RPi 5 16KB pages — see commit 33e08b9)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .

# Build the frontend (runs on Pi or rsync dist/ from Mac)
cd frontend && npm install && npm run build && cd ..

# Configure
cp .env.example .env
# Set INGEST_SOURCE=gdelt (or keep mock for testing)

# Enable auto-login via raspi-config → System → Auto Login
```

### Install services

```bash
cd ~/Flashpoint
bash deploy/pi/install.sh          # use --dry-run to preview

systemctl --user enable flashpoint-backend
systemctl --user start flashpoint-backend
# Dashboard autostart activates on next login
```

### Boot flow

```
Power on
  └── Pi OS boots → auto-login (pi)
        ├── systemd --user
        │     └── flashpoint-backend.service → uvicorn :8000
        └── XDG autostart → pi_start.sh
              └── python3 -m desktop.app.main (FULLSCREEN, MANAGED)
                    ├── CONNECTING overlay (native Qt)
                    ├── polls /api/v1/health every 2s (up to ~20s)
                    ├── LOADING_WEBVIEW → QWebEngineView loads :8000
                    └── READY — fullscreen dashboard
```

</details>

---

## Roadmap

| Milestone | Status |
|---|---|
| FastAPI backend, SQLite models, REST API | Done |
| React/Vite V3 workstation frontend | Done |
| GDELT + Event Registry ingestion, classifier, deduper, corroboration | Done |
| Evidence/Observation provenance layer + observation APIs | Done |
| Hotspot clustering, scoring, trend analysis, naming | Done |
| PySide6 desktop shell + Qt compat layer (Milestone A) | Done |
| Desktop runtime orchestration + Pi seam configuration | Done |
| Pi backend service scaffolding (systemd + XDG autostart) | Done |
| Pi frontend delivery (StaticFiles, `pi_start.sh`) | Done |
| **Pi hardware validation** — boot → READY on physical hardware | Done |
| Landscape/touch workstation tuning | In progress |
| Stage 1.5 data quality upgrade | Done |
| Stage 1.5 live feed operational tuning | In progress |

---

## License

No license has been applied to this repository yet. All rights reserved by default.
