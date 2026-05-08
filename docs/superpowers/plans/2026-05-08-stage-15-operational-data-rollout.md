# Stage 1.5 Operational Data Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Stage 1.5 infrastructure into live operating data through NWS, curated regional RSS, a Census-backed geocoder, eval fixtures, and Pi rollout.

**Architecture:** Keep SQLite/FastAPI/React/Pi architecture. Sources continue to create evidence and observations first; only confirmed/promoted events affect hotspots. Use committed registry/eval/gazetteer artifacts so future agents can reproduce the rollout.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, APScheduler, React/Vite, PySide6 shell, U.S. Census Gazetteer CSV/ZIP data, pytest.

---

### Task 1: RSS Registry And Manual Ingest Helper

**Files:**
- Create: `backend/app/data/rss_feed_registry.csv`
- Create: `backend/app/services/ingestion/rss_registry.py`
- Create: `scripts/run_observation_ingest.sh`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [x] Write failing tests for enabled regional feeds, missing allowlist rejection, registry-backed local news fetch, and helper validation.
- [x] Implement registry loader with enabled feed validation.
- [x] Teach LocalNewsSource to use enabled registry feeds when `.env` feed URLs are empty.
- [x] Add manual observation ingest helper for `nws|bluesky|mastodon|local_news|acled`.
- [x] Verify targeted tests pass.

### Task 2: Census Gazetteer And Alias Geocoding

**Files:**
- Create: `scripts/generate_us_gazetteer.py`
- Create: `backend/app/data/us_location_aliases.csv`
- Modify: `backend/app/data/us_locations.csv`
- Modify: `backend/app/services/geocoding.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [x] Write failing tests for alias and county resolution.
- [x] Add reproducible Census 2020 Places/Counties generation script.
- [x] Generate committed `us_locations.csv`.
- [x] Add alias and county fallback geocoding while preserving city/state ambiguity rejection.
- [x] Verify targeted tests pass.

### Task 3: Eval Smoke Dataset

**Files:**
- Create: `backend/tests/fixtures/stage15_eval_cases.json`
- Create: `backend/app/services/eval/stage15_eval.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [x] Add 30-case eval fixture covering real unrest, social-only, bad-location, false-positive, and duplicate examples.
- [x] Add report command: `cd backend && ../.venv/bin/python -m app.services.eval.stage15_eval`.
- [x] Assert stable totals and zero false event creation in tests.

### Task 4: Docs, Verification, Pi Rollout, Merge

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/data-upgrade-plan.md`
- Modify: `docs/context.md`

- [x] Document NWS/local RSS config and deferred social/ACLED sources.
- [x] Run full backend/frontend verification.
- [x] Push branch, merge to `main`, push `main`.
- [x] Fast-forward Pi to `main`.
- [x] Back up Pi `.env`, apply NWS + regional RSS config, restart backend, run manual `nws` and `local_news` ingest, verify `/api/v1/sources/status`.
