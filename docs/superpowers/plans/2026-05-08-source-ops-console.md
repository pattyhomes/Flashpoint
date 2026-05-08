# Source Operations Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stage 1.5 data upgrade visibly operational by adding source run history and touch-safe Run Now controls to the Sources rail.

**Architecture:** Keep ingestion source execution server-side and evidence-first. The backend exposes recent `IngestRun` history and a guarded run-now endpoint for observation sources only; the frontend fetches that history, lets the operator trigger a safe source ingest, and refreshes status/history after the run is queued. No source run creates events directly except through existing safe auto-link/auto-promote rules.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, pytest, React/Vite, existing V3 workstation CSS.

---

## File Structure

- Modify `backend/app/schemas.py`
  - Add `SourceRunOut`, `SourceRunHistoryResponse`, and `SourceRunRequestResponse`.
  - Add `runnable: bool` to `SourceStatusOut`.
- Modify `backend/app/routes/sources.py`
  - Add `GET /api/v1/sources/runs?source_name=&limit=`.
  - Add `POST /api/v1/sources/{source_name}/run`.
  - Mark observation sources as runnable in `/sources/status`.
- Modify `backend/tests/test_stage15_operational_rollout.py`
  - Add API tests for run history, runnable status, run-now success, and run-now rejection for unknown/non-observation sources.
- Modify `frontend/src/services/api.js`
  - Add `fetchSourceRuns()` and `runSourceNow()`.
- Modify `frontend/src/App.jsx`
  - Track source run history, source run busy/error state, refresh helpers, and run-now handler.
- Modify `frontend/src/components/workstation/RightRail.jsx`
  - Render Run Now controls per runnable source and a compact recent runs panel.
- Modify `frontend/src/styles/components.css`
  - Add touch-safe styles for source action buttons and run history rows.
- Modify `README.md`, `docs/context.md`, `docs/data-upgrade-plan.md`
  - Document the new source operations loop.

---

### Task 1: Backend Source Run History API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routes/sources.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write failing tests**

Append these tests to `backend/tests/test_stage15_operational_rollout.py`:

```python
def test_sources_status_marks_observation_sources_runnable(client, db_engine):
    from app.models import IngestRun
    from app.utils.time import utcnow_naive

    Session = sessionmaker(bind=db_engine)
    db = Session()
    db.add(IngestRun(
        started_at=utcnow_naive(),
        finished_at=utcnow_naive(),
        status="success",
        ingest_source="local_news",
    ))
    db.add(IngestRun(
        started_at=utcnow_naive(),
        finished_at=utcnow_naive(),
        status="success",
        ingest_source="gdelt",
    ))
    db.commit()
    db.close()

    response = client.get("/api/v1/sources/status")
    assert response.status_code == 200
    rows = {row["source_name"]: row for row in response.json()["sources"]}
    assert rows["local_news"]["runnable"] is True
    assert rows["gdelt"]["runnable"] is False
```

```python
def test_sources_runs_endpoint_returns_recent_runs(client, db_engine):
    from app.models import IngestRun
    from app.utils.time import utcnow_naive

    Session = sessionmaker(bind=db_engine)
    db = Session()
    for index, source_name in enumerate(["local_news", "nws", "local_news"]):
        db.add(IngestRun(
            started_at=utcnow_naive(),
            finished_at=utcnow_naive(),
            status="success",
            ingest_source=source_name,
            records_fetched=index + 1,
            observations_inserted=index,
            records_rejected=1,
            reject_counts_json=json.dumps({"classified_out": 1}),
            sample_records_json=json.dumps([{"category": "classified_out", "title": f"sample {index}"}]),
        ))
    db.commit()
    db.close()

    response = client.get("/api/v1/sources/runs?source_name=local_news&limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert all(row["source_name"] == "local_news" for row in payload["runs"])
    assert payload["runs"][0]["sample_records"][0]["category"] == "classified_out"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_sources_status_marks_observation_sources_runnable tests/test_stage15_operational_rollout.py::test_sources_runs_endpoint_returns_recent_runs -q
```

Expected: fail because `runnable` and `/sources/runs` do not exist.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas.py`, add:

```python
class SourceRunOut(BaseModel):
    id: int
    source_name: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    events_inserted: int
    records_fetched: int
    evidence_inserted: int
    observations_inserted: int
    records_rejected: int
    reject_counts: dict[str, int] = {}
    sample_records: list[SourceSampleOut] = []
    error_message: str | None = None


class SourceRunHistoryResponse(BaseModel):
    runs: list[SourceRunOut]
    total: int
    limit: int
    source_name: str | None = None
    generated_at: datetime
```

Add to `SourceStatusOut`:

```python
runnable: bool = False
```

- [ ] **Step 4: Add route helpers**

In `backend/app/routes/sources.py`, import:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

Add:

```python
RUNNABLE_OBSERVATION_SOURCES = {"nws", "bluesky", "mastodon", "local_news", "acled"}
```

Add to `_source_payload()`:

```python
"runnable": source_name in RUNNABLE_OBSERVATION_SOURCES,
```

Add helper:

```python
def _run_payload(run: IngestRun) -> dict:
    return {
        "id": run.id,
        "source_name": run.ingest_source,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "events_inserted": run.events_inserted,
        "records_fetched": run.records_fetched,
        "evidence_inserted": run.evidence_inserted,
        "observations_inserted": run.observations_inserted,
        "records_rejected": run.records_rejected,
        "reject_counts": _json_dict(run.reject_counts_json),
        "sample_records": _json_list(run.sample_records_json),
        "error_message": run.error_message,
    }
```

- [ ] **Step 5: Add run history endpoint**

In `backend/app/routes/sources.py`, add:

```python
@router.get("/runs", response_model=SourceRunHistoryResponse)
def source_runs(
    source_name: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(IngestRun).filter(IngestRun.ingest_source.isnot(None))
    if source_name:
        query = query.filter(IngestRun.ingest_source == source_name)
    total = query.count()
    rows = query.order_by(IngestRun.started_at.desc()).limit(limit).all()
    return {
        "runs": [_run_payload(row) for row in rows],
        "total": total,
        "limit": limit,
        "source_name": source_name,
        "generated_at": utcnow_naive(),
    }
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_sources_status_marks_observation_sources_runnable tests/test_stage15_operational_rollout.py::test_sources_runs_endpoint_returns_recent_runs -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routes/sources.py backend/tests/test_stage15_operational_rollout.py
git commit -m "feat: add source run history API"
```

---

### Task 2: Backend Run-Now API

**Files:**
- Modify: `backend/app/routes/sources.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_sources_run_now_queues_observation_ingest(client):
    with patch("app.routes.sources.run_observation_source_ingestion") as run_ingest:
        response = client.post("/api/v1/sources/local_news/run")

    assert response.status_code == 200
    assert response.json()["source_name"] == "local_news"
    assert response.json()["status"] == "queued"
    run_ingest.assert_called_once_with("local_news")
```

```python
def test_sources_run_now_rejects_non_observation_source(client):
    response = client.post("/api/v1/sources/gdelt/run")
    assert response.status_code == 400
    assert "not runnable" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_sources_run_now_queues_observation_ingest tests/test_stage15_operational_rollout.py::test_sources_run_now_rejects_non_observation_source -q
```

Expected: fail because endpoint does not exist.

- [ ] **Step 3: Add response schema**

In `backend/app/schemas.py`, add:

```python
class SourceRunRequestResponse(BaseModel):
    source_name: str
    status: str
    message: str
```

- [ ] **Step 4: Add endpoint**

In `backend/app/routes/sources.py`, import:

```python
from app.jobs.seed import run_observation_source_ingestion
```

Add:

```python
@router.post("/{source_name}/run", response_model=SourceRunRequestResponse)
def run_source_now(source_name: str):
    if source_name not in RUNNABLE_OBSERVATION_SOURCES:
        raise HTTPException(status_code=400, detail=f"Source {source_name!r} is not runnable from the operator console")
    run_observation_source_ingestion(source_name)
    return {
        "source_name": source_name,
        "status": "queued",
        "message": f"{source_name} ingest completed",
    }
```

Note: This endpoint runs synchronously for deterministic local behavior. The Pi remains usable because these sources are bounded by config and existing source limits.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_sources_run_now_queues_observation_ingest tests/test_stage15_operational_rollout.py::test_sources_run_now_rejects_non_observation_source -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routes/sources.py backend/tests/test_stage15_operational_rollout.py
git commit -m "feat: add source run now endpoint"
```

---

### Task 3: Frontend API And App State

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Add API client functions**

In `frontend/src/services/api.js`, add:

```javascript
export const fetchSourceRuns = (sourceName = null, limit = 20) => {
  const params = new URLSearchParams()
  if (sourceName) params.set('source_name', sourceName)
  params.set('limit', String(limit))
  return request(`/sources/runs?${params.toString()}`)
}
export const runSourceNow = (sourceName) => request(`/sources/${sourceName}/run`, { method: 'POST' })
```

- [ ] **Step 2: Import API functions in App**

In `frontend/src/App.jsx`, add imports:

```javascript
fetchSourceRuns,
runSourceNow,
```

- [ ] **Step 3: Add state**

After `sourceStatus` state:

```javascript
const [sourceRuns, setSourceRuns] = useState([])
const [sourceRunsLoading, setSourceRunsLoading] = useState(false)
const [sourceRunBusy, setSourceRunBusy] = useState(null)
const [sourceRunError, setSourceRunError] = useState(null)
```

- [ ] **Step 4: Add refresh helper**

Add:

```javascript
function refreshSourceOps() {
  setSourceRunsLoading(true)
  return Promise.all([fetchSourcesStatus(), fetchSourceRuns(null, 20)])
    .then(([sources, runs]) => {
      setSourceStatus(sources)
      setSourceRuns(runs.runs || [])
      setSourceRunError(null)
    })
    .catch(error => {
      console.error('[Flashpoint] source ops error:', error)
      setSourceRunError('Source operations unavailable')
    })
    .finally(() => setSourceRunsLoading(false))
}
```

- [ ] **Step 5: Load source runs in initial fetch and polling**

Add `fetchSourceRuns(null, 20)` to initial and poll `Promise.all()` calls, and set:

```javascript
setSourceRuns(sourceRunPage.runs || [])
```

- [ ] **Step 6: Add run-now handler**

Add:

```javascript
function handleRunSource(sourceName) {
  setSourceRunBusy(sourceName)
  setSourceRunError(null)
  return runSourceNow(sourceName)
    .then(() => Promise.all([refreshSourceOps(), refreshObservations(activeExceptionCategoryRef.current), refreshConfirmedData()]))
    .catch(error => {
      console.error('[Flashpoint] source run error:', error)
      setSourceRunError(`Unable to run ${sourceName}`)
    })
    .finally(() => setSourceRunBusy(null))
}
```

- [ ] **Step 7: Pass props to RightRail**

Add props:

```jsx
sourceRuns={sourceRuns}
sourceRunsLoading={sourceRunsLoading}
sourceRunBusy={sourceRunBusy}
sourceRunError={sourceRunError}
onRunSource={handleRunSource}
```

- [ ] **Step 8: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/services/api.js frontend/src/App.jsx
git commit -m "feat: wire source operations state"
```

---

### Task 4: Frontend Sources Rail Operations UI

**Files:**
- Modify: `frontend/src/components/workstation/RightRail.jsx`
- Modify: `frontend/src/styles/components.css`

- [ ] **Step 1: Add relative run time helper**

Import:

```javascript
import { relativeTime } from '../../utils/time.js'
```

- [ ] **Step 2: Add SourceRuns component**

Add below `SourceHealth`:

```jsx
function SourceRuns({ runs, loading }) {
  return (
    <div className="source-runs">
      <div className="rail-section-title">
        <span>Recent Runs</span>
        <b>{loading ? 'sync' : formatCount(runs.length)}</b>
      </div>
      <div className="source-runs__list">
        {runs.length === 0 ? (
          <span className="empty-note">No run history yet.</span>
        ) : runs.slice(0, 8).map(run => (
          <div className={`source-run source-run--${run.status}`} key={run.id}>
            <div>
              <b>{labelize(run.source_name)}</b>
              <span>{relativeTime(run.finished_at || run.started_at)}</span>
            </div>
            <dl>
              <dt>F</dt><dd>{formatCount(run.records_fetched)}</dd>
              <dt>A</dt><dd>{formatCount(run.observations_inserted)}</dd>
              <dt>R</dt><dd>{formatCount(run.records_rejected)}</dd>
            </dl>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add Run Now button in SourceHealth**

Update `SourceHealth` signature:

```javascript
function SourceHealth({ sourceStatus, systemStatus, sourceRunBusy, onRunSource })
```

Inside each source row, below quality chips, add:

```jsx
{source.runnable && (
  <button
    type="button"
    className="source-row__run"
    disabled={sourceRunBusy === source.source_name}
    onClick={() => onRunSource(source.source_name)}
  >
    {sourceRunBusy === source.source_name ? 'RUNNING' : 'RUN NOW'}
  </button>
)}
```

- [ ] **Step 4: Wire props in RightRail**

Add to props:

```javascript
sourceRuns,
sourceRunsLoading,
sourceRunBusy,
sourceRunError,
onRunSource,
```

Render:

```jsx
{sourceRunError && <span className="empty-note empty-note--error">{sourceRunError}</span>}
<SourceHealth
  sourceStatus={sourceStatus}
  systemStatus={systemStatus}
  sourceRunBusy={sourceRunBusy}
  onRunSource={onRunSource}
/>
<SourceRuns runs={sourceRuns || []} loading={sourceRunsLoading} />
```

- [ ] **Step 5: Add CSS**

Add to `frontend/src/styles/components.css`:

```css
.source-row__run {
  width: fit-content;
  min-height: 34px;
  margin-top: 6px;
  padding: 0 10px;
  border: 1px solid rgba(109,179,255,0.32);
  background: rgba(109,179,255,0.10);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  touch-action: manipulation;
}

.source-row__run:disabled {
  opacity: 0.55;
}

.source-runs {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--line);
}

.source-runs__list {
  max-height: 150px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.source-run {
  min-height: 38px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--line);
}

.source-run > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.source-run b,
.source-run span,
.source-run dt,
.source-run dd {
  font-family: var(--font-mono);
  font-size: 9px;
}

.source-run b {
  color: var(--t-0);
  font-weight: 500;
  text-transform: uppercase;
}

.source-run span,
.source-run dt {
  color: var(--t-2);
  text-transform: uppercase;
}

.source-run dl {
  display: grid;
  grid-template-columns: repeat(3, auto auto);
  gap: 3px 5px;
  margin: 0;
}

.source-run dd {
  margin: 0;
  color: var(--t-0);
}

.source-run dt {
  margin: 0;
}

.source-run--failed {
  background: rgba(231,89,73,0.08);
}
```

- [ ] **Step 6: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/workstation/RightRail.jsx frontend/src/styles/components.css
git commit -m "feat: add source operations rail"
```

---

### Task 5: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/context.md`
- Modify: `docs/data-upgrade-plan.md`

- [ ] **Step 1: Update docs**

In `README.md`, update backend test count to the actual final count and add a short line near the source quality report:

```markdown
The Sources rail also includes recent run history and Run Now controls for bounded observation sources (`nws`, `local_news`, and future configured weak-signal sources).
```

In `docs/context.md`, add:

```markdown
The Sources rail now doubles as the Stage 1.5 source operations console: it
shows run history, quality samples, and Run Now controls for bounded observation
sources. Confirmed-source and hotspot rules remain unchanged.
```

In `docs/data-upgrade-plan.md`, update the recommended next sprint list:

```markdown
1. Run `nws` and `local_news` from the Sources rail after deploy, then inspect
   recent run history and source samples.
2. Add or remove regional RSS feeds based on source quality samples, not just
   aggregate rejection counts.
3. Expand eval fixtures with real false positives from the Pi source samples.
4. Decide whether Bluesky should be enabled as a weak signal source.
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend lint and build**

Run:

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: pass. Existing Vite chunk-size warning is acceptable.

- [ ] **Step 4: Run whitespace and status checks**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; branch contains only intended committed work.

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/context.md docs/data-upgrade-plan.md docs/superpowers/plans/2026-05-08-source-ops-console.md
git commit -m "docs: document source operations console"
```

---

## Self-Review

Spec coverage:

- Sticks to Stage 1.5 upgrade plan: source health, real feed operations, source-quality samples, and eval/tuning workflow.
- Meaningful visible progress: Sources rail gets recent run history and Run Now controls.
- Safety: run-now is limited to observation sources and still uses existing evidence/observation workflow.
- Pi constraints: no heavy AI, no Postgres, no browser kiosk changes.

Placeholder scan:

- No `TBD`, `TODO`, or open-ended “add tests” placeholders remain.

Type consistency:

- API uses `SourceRunOut`, `SourceRunHistoryResponse`, and `SourceRunRequestResponse`.
- Frontend uses `sourceRuns`, `sourceRunBusy`, and `sourceRunError`.
- Backend endpoint names are `/api/v1/sources/runs` and `/api/v1/sources/{source_name}/run`.

