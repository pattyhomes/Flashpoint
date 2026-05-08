# Live Data Tuning Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Stage 1.5 live source tuning operational by persisting source diagnostic samples, fixing the regional RSS feed path/redirect behavior, surfacing rejection examples in the Sources rail, and documenting the tuning loop.

**Architecture:** Keep SQLite and the existing evidence-first ingestion pipeline. Observation sources may attach bounded `sample_records` diagnostics to their in-memory `stats`; `run_observation_source_ingestion()` persists those diagnostics on `IngestRun`; `/api/v1/sources/status` exposes them to the V3 Sources rail and a local report script. Diagnostics are operator metadata only; they do not create events, observations, map signals, or hotspot score.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite additive migrations, pytest, React/Vite, shell/Python helper scripts.

---

## File Structure

- Modify `backend/app/models.py`
  - Add `IngestRun.sample_records_json: Text | None`.
- Modify `backend/app/main.py`
  - Add additive SQLite migration for `ingest_runs.sample_records_json`.
- Modify `backend/app/schemas.py`
  - Add a small `SourceSampleOut` schema and `SourceStatusOut.sample_records`.
- Modify `backend/app/jobs/seed.py`
  - Persist bounded source stats samples into `IngestRun.sample_records_json`.
- Modify `backend/app/routes/sources.py`
  - Parse sample records and expose derived quality fields: accepted/rejected counts already exist, plus `sample_records`.
- Modify `backend/app/services/ingestion/local_news_source.py`
  - Preserve the RSS redirect fix.
  - Collect diagnostic samples for feed fetch errors, parse errors, domain rejections, article fetch errors, final-domain rejections, classified-out records, bad-location records, and accepted candidates.
- Modify `backend/app/data/rss_feed_registry.csv`
  - Use LAist’s XML feed URL `https://laist.com/news.rss`.
- Modify `backend/tests/test_stage15_operational_rollout.py`
  - Add tests for LAist feed URL, redirected Texas Tribune article fetches, local news diagnostic samples, ingest-run sample persistence, and `/sources/status` sample output.
- Create `scripts/report_source_quality.py`
  - Print the latest source run metrics and samples from the configured SQLite database as JSON.
- Modify `frontend/src/components/workstation/RightRail.jsx`
  - Render acceptance rate, top reject bucket, and diagnostic samples in each source row.
- Modify `frontend/src/styles/components.css`
  - Add compact, touch-safe styles for source diagnostics.
- Modify `README.md`
  - Update test count and mention the source quality report helper.
- Modify `docs/context.md`
  - Record current branch priority and the new live-data tuning observability loop.
- Modify `docs/data-upgrade-plan.md`
  - Move “review live ingest runs” from vague next step into concrete operator workflow.

---

### Task 1: Preserve Regional RSS Fixes

**Files:**
- Modify: `backend/app/data/rss_feed_registry.csv`
- Modify: `backend/app/services/ingestion/local_news_source.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write/confirm failing registry test**

Add this assertion to `test_rss_registry_loads_enabled_regional_pilot_feeds`:

```python
assert any(feed.name == "LAist" and feed.feed_url == "https://laist.com/news.rss" for feed in feeds)
```

- [ ] **Step 2: Write/confirm failing redirect test**

Add this test to `backend/tests/test_stage15_operational_rollout.py`:

```python
def test_local_news_follows_feed_redirect_links_to_allowlisted_article_domain():
    from app.services.ingestion.local_news_source import LocalNewsSource

    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>tt-1</guid>
        <title>Protest update after downtown gathering</title>
        <link>https://feeds.texastribune.org/link/16799/tt-1/austin-road-closure</link>
        <description>Brief update from the newsroom.</description>
        <pubDate>Thu, 07 May 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    feed_response = MagicMock(text=feed)
    feed_response.raise_for_status.return_value = None
    robots_response = MagicMock(text="User-agent: *\nAllow: /\n", status_code=200)
    robots_response.raise_for_status.return_value = None
    article_response = MagicMock(
        text="<article>Protesters set up a road blockade in downtown Austin, TX.</article>",
        url="https://www.texastribune.org/2026/05/07/austin-road-closure/",
    )
    article_response.raise_for_status.return_value = None

    def fake_get(url, **kwargs):
        if url == "https://feeds.texastribune.org/feeds/main/":
            return feed_response
        if url == "https://feeds.texastribune.org/robots.txt":
            return robots_response
        if url == "https://feeds.texastribune.org/link/16799/tt-1/austin-road-closure":
            if not kwargs.get("follow_redirects"):
                raise RuntimeError("redirect was not followed")
            return article_response
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", ""),
        patch("app.config.settings.local_news_allowed_domains", ""),
        patch("app.config.settings.local_news_max_records", 5),
        patch("app.services.ingestion.rss_registry.load_enabled_local_news_feeds") as load_feeds,
        patch("app.services.ingestion.local_news_source.httpx.get", side_effect=fake_get),
    ):
        load_feeds.return_value = [
            type(
                "Feed",
                (),
                {
                    "name": "Texas Tribune",
                    "feed_url": "https://feeds.texastribune.org/feeds/main/",
                    "allowed_domains": ("feeds.texastribune.org", "www.texastribune.org"),
                },
            )()
        ]
        source = LocalNewsSource()
        candidates = source.fetch()

    assert len(candidates) == 1
    assert candidates[0].candidate_event_type == "protest"
    assert candidates[0].city == "Austin"
    assert candidates[0].state == "TX"
    assert "article_fetch_error" not in source.stats["reject_counts"]
```

- [ ] **Step 3: Run test to verify failure on old code**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_rss_registry_loads_enabled_regional_pilot_feeds tests/test_stage15_operational_rollout.py::test_local_news_follows_feed_redirect_links_to_allowlisted_article_domain -q
```

Expected before implementation: fails because LAist still points at `rss-feed` and article requests do not pass `follow_redirects=True`.

- [ ] **Step 4: Implement registry and redirect fixes**

Set LAist row in `backend/app/data/rss_feed_registry.csv`:

```csv
LAist,https://laist.com/news.rss,laist.com,Los Angeles CA,news,true,Regional pilot feed
```

Update `LocalNewsSource.fetch()` feed request:

```python
response = httpx.get(
    feed_url,
    headers={"User-Agent": settings.local_news_user_agent},
    timeout=30,
    follow_redirects=True,
)
```

Update `_fetch_article()` article request and final-domain check:

```python
response = httpx.get(
    url,
    headers={"User-Agent": settings.local_news_user_agent},
    timeout=30,
    follow_redirects=True,
)
response.raise_for_status()
raw_final_url = getattr(response, "url", None)
final_url = str(raw_final_url) if isinstance(raw_final_url, (str, httpx.URL)) else url
if _domain(final_url) not in allowed_domains:
    self._reject("article_domain_not_allowed")
    return ""
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py -q
```

Expected: all tests in file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/rss_feed_registry.csv backend/app/services/ingestion/local_news_source.py backend/tests/test_stage15_operational_rollout.py
git commit -m "fix: improve regional RSS article fetching"
```

---

### Task 2: Persist Ingest Diagnostic Samples

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/jobs/seed.py`
- Modify: `backend/app/routes/sources.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write failing persistence/API tests**

Append these tests to `backend/tests/test_stage15_operational_rollout.py`:

```python
def test_observation_source_ingestion_persists_sample_records(db_engine):
    import json
    import app.jobs.seed as seed_module
    from app.models import IngestRun

    Session = sessionmaker(bind=db_engine)

    class FakeSource:
        stats = {
            "fetched": 2,
            "rejected": 2,
            "reject_counts": {"classified_out": 2},
            "sample_records": [
                {
                    "category": "classified_out",
                    "source_name": "LAist",
                    "title": "City council approves budget",
                    "source_url": "https://laist.com/news/example",
                    "reason": "No unrest classifier signal.",
                }
            ],
        }

        def fetch(self):
            return []

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch.dict(seed_module.OBSERVATION_SOURCE_MAP, {"local_news": ("local_news", FakeSource)}),
    ):
        seed_module.run_observation_source_ingestion("local_news")

    db = Session()
    run = db.query(IngestRun).filter(IngestRun.ingest_source == "local_news").one()
    samples = json.loads(run.sample_records_json)
    db.close()

    assert samples[0]["category"] == "classified_out"
    assert samples[0]["title"] == "City council approves budget"
```

```python
def test_sources_status_exposes_sample_records(client):
    import json
    from app.database import SessionLocal
    from app.models import IngestRun
    from app.utils.time import utcnow_naive

    db = SessionLocal()
    db.add(IngestRun(
        started_at=utcnow_naive(),
        finished_at=utcnow_naive(),
        status="success",
        ingest_source="local_news",
        records_fetched=1,
        records_rejected=1,
        reject_counts_json=json.dumps({"classified_out": 1}),
        sample_records_json=json.dumps([
            {"category": "classified_out", "source_name": "LAist", "title": "Budget story"}
        ]),
    ))
    db.commit()
    db.close()

    response = client.get("/api/v1/sources/status")
    assert response.status_code == 200
    source = next(row for row in response.json()["sources"] if row["source_name"] == "local_news")
    assert source["sample_records"][0]["title"] == "Budget story"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_observation_source_ingestion_persists_sample_records tests/test_stage15_operational_rollout.py::test_sources_status_exposes_sample_records -q
```

Expected before implementation: fails because `sample_records_json` and `sample_records` do not exist.

- [ ] **Step 3: Add model and migration**

In `backend/app/models.py`, add to `IngestRun`:

```python
sample_records_json: Mapped[str|None] = mapped_column(Text, nullable=True)
```

In `backend/app/main.py`, add to the migration list:

```python
"ALTER TABLE ingest_runs ADD COLUMN sample_records_json TEXT",
```

- [ ] **Step 4: Add schemas**

In `backend/app/schemas.py`, add:

```python
class SourceSampleOut(BaseModel):
    category: str
    source_name: str | None = None
    title: str | None = None
    source_url: str | None = None
    reason: str | None = None
```

Then add to `SourceStatusOut`:

```python
sample_records: list[SourceSampleOut] = []
```

- [ ] **Step 5: Persist bounded samples**

In `run_observation_source_ingestion()` after `reject_counts_json` assignment, add:

```python
run.sample_records_json = json.dumps(
    _bounded_sample_records(stats.get("sample_records", [])),
    sort_keys=True,
    separators=(",", ":"),
)
```

Add helper in `backend/app/jobs/seed.py`:

```python
def _bounded_sample_records(value, limit: int = 8) -> list[dict]:
    if not isinstance(value, list):
        return []
    samples = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        samples.append({
            "category": str(item.get("category") or "sample")[:64],
            "source_name": str(item.get("source_name") or "")[:128] or None,
            "title": str(item.get("title") or "")[:180] or None,
            "source_url": str(item.get("source_url") or "")[:512] or None,
            "reason": str(item.get("reason") or "")[:220] or None,
        })
    return samples
```

- [ ] **Step 6: Expose samples from sources route**

In `backend/app/routes/sources.py`, add:

```python
"sample_records": _json_list(last_run.sample_records_json if last_run else None),
```

Add helper:

```python
def _json_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_observation_source_ingestion_persists_sample_records tests/test_stage15_operational_rollout.py::test_sources_status_exposes_sample_records -q
```

Expected: both pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/app/main.py backend/app/schemas.py backend/app/jobs/seed.py backend/app/routes/sources.py backend/tests/test_stage15_operational_rollout.py
git commit -m "feat: persist source diagnostic samples"
```

---

### Task 3: Collect Local News Diagnostic Samples

**Files:**
- Modify: `backend/app/services/ingestion/local_news_source.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write failing Local News diagnostic sample test**

Add:

```python
def test_local_news_records_diagnostic_samples_for_rejections():
    from app.services.ingestion.local_news_source import LocalNewsSource

    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>laist-noise</guid>
        <title>Best weekend restaurants in Los Angeles</title>
        <link>https://laist.com/news/food</link>
        <description>Restaurant week begins in Los Angeles, CA.</description>
      </item>
    </channel></rss>
    """
    feed_response = MagicMock(text=feed)
    feed_response.raise_for_status.return_value = None
    robots_response = MagicMock(text="User-agent: *\nAllow: /\n", status_code=200)
    robots_response.raise_for_status.return_value = None
    article_response = MagicMock(
        text="<article>Food and lifestyle coverage.</article>",
        url="https://laist.com/news/food",
    )
    article_response.raise_for_status.return_value = None

    def fake_get(url, **_kwargs):
        if url == "https://laist.com/news.rss":
            return feed_response
        if url == "https://laist.com/robots.txt":
            return robots_response
        if url == "https://laist.com/news/food":
            return article_response
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", ""),
        patch("app.config.settings.local_news_allowed_domains", ""),
        patch("app.config.settings.local_news_max_records", 5),
        patch("app.services.ingestion.rss_registry.load_enabled_local_news_feeds") as load_feeds,
        patch("app.services.ingestion.local_news_source.httpx.get", side_effect=fake_get),
    ):
        load_feeds.return_value = [
            type("Feed", (), {"name": "LAist", "feed_url": "https://laist.com/news.rss", "allowed_domains": ("laist.com",)})()
        ]
        source = LocalNewsSource()
        candidates = source.fetch()

    assert candidates == []
    assert source.stats["sample_records"][0]["category"] == "classified_out"
    assert source.stats["sample_records"][0]["title"] == "Best weekend restaurants in Los Angeles"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_local_news_records_diagnostic_samples_for_rejections -q
```

Expected before implementation: fails because `sample_records` is not populated.

- [ ] **Step 3: Add sample collection helpers**

In `LocalNewsSource.__init__`, initialize:

```python
self.stats = {"fetched": 0, "rejected": 0, "reject_counts": {}, "sample_records": []}
```

Replace `_reject` with:

```python
def _reject(self, category: str, sample: dict | None = None):
    self.stats["rejected"] += 1
    counts = self.stats["reject_counts"]
    counts[category] = counts.get(category, 0) + 1
    if sample and len(self.stats["sample_records"]) < 8:
        self.stats["sample_records"].append({
            "category": category,
            "source_name": sample.get("source_name"),
            "title": sample.get("title"),
            "source_url": sample.get("source_url"),
            "reason": sample.get("reason"),
        })
```

Add helper:

```python
def _sample(self, category: str, title: str | None = None, link: str | None = None, feed_name: str | None = None, reason: str | None = None):
    return {
        "category": category,
        "source_name": feed_name or "Local News",
        "title": (title or "Untitled")[:180],
        "source_url": link,
        "reason": reason,
    }
```

- [ ] **Step 4: Pass samples at rejection points**

For classified-out:

```python
self._reject("classified_out", self._sample(
    "classified_out",
    title=title,
    link=link,
    feed_name=feed_name,
    reason="No unrest classifier signal.",
))
```

For bad-location:

```python
self._reject("bad_location", self._sample(
    "bad_location",
    title=title,
    link=link,
    feed_name=feed_name,
    reason="Local geocoder could not resolve a city/state.",
))
```

For article fetch/final-domain failures, pass title-less samples if available from caller only when the function signature is updated to `_fetch_article(url, allowed_domains, title=None, feed_name=None)`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_local_news_records_diagnostic_samples_for_rejections -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ingestion/local_news_source.py backend/tests/test_stage15_operational_rollout.py
git commit -m "feat: collect local news rejection samples"
```

---

### Task 4: Add Source Quality Report Helper

**Files:**
- Create: `scripts/report_source_quality.py`
- Test: `backend/tests/test_stage15_operational_rollout.py`

- [ ] **Step 1: Write failing script smoke test**

Add:

```python
def test_source_quality_report_helper_exists_and_mentions_samples():
    script = Path("scripts/report_source_quality.py")
    text = script.read_text(encoding="utf-8")
    assert "sample_records_json" in text
    assert "records_rejected" in text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_source_quality_report_helper_exists_and_mentions_samples -q
```

Expected before implementation: fails because the script does not exist.

- [ ] **Step 3: Create script**

Create `scripts/report_source_quality.py`:

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal  # noqa: E402
from app.models import IngestRun  # noqa: E402


def _json(value, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def main():
    db = SessionLocal()
    try:
        source_names = [
            row[0]
            for row in db.query(IngestRun.ingest_source)
            .filter(IngestRun.ingest_source.isnot(None))
            .distinct()
            .all()
        ]
        report = []
        for source_name in sorted(source_names):
            run = (
                db.query(IngestRun)
                .filter(IngestRun.ingest_source == source_name)
                .order_by(IngestRun.started_at.desc())
                .first()
            )
            if not run:
                continue
            report.append({
                "source_name": source_name,
                "status": run.status,
                "last_run_at": run.started_at.isoformat() if run.started_at else None,
                "records_fetched": run.records_fetched,
                "observations_inserted": run.observations_inserted,
                "records_rejected": run.records_rejected,
                "reject_counts": _json(run.reject_counts_json, {}),
                "sample_records": _json(run.sample_records_json, []),
            })
        print(json.dumps({"sources": report}, indent=2, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Make script executable**

Run:

```bash
chmod +x scripts/report_source_quality.py
```

- [ ] **Step 5: Run smoke test**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_stage15_operational_rollout.py::test_source_quality_report_helper_exists_and_mentions_samples -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/report_source_quality.py backend/tests/test_stage15_operational_rollout.py
git commit -m "feat: add source quality report helper"
```

---

### Task 5: Render Source Diagnostics In The Sources Rail

**Files:**
- Modify: `frontend/src/components/workstation/RightRail.jsx`
- Modify: `frontend/src/styles/components.css`

- [ ] **Step 1: Update source row markup**

In `SourceHealth`, compute:

```jsx
const accepted = source.observations_inserted || 0
const fetched = source.records_fetched || 0
const rejected = source.records_rejected || 0
const acceptanceRate = fetched > 0 ? Math.round((accepted / fetched) * 100) : 0
const rejectEntries = Object.entries(source.reject_counts || {}).sort((a, b) => b[1] - a[1])
const topReject = rejectEntries[0]
const samples = source.sample_records || []
```

Inside each `.source-row`, add:

```jsx
<div className="source-row__quality">
  <span>{acceptanceRate}% accepted</span>
  {topReject && <span>{labelize(topReject[0])}: {formatCount(topReject[1])}</span>}
</div>
{samples.length > 0 && (
  <div className="source-row__samples">
    {samples.slice(0, 3).map((sample, index) => (
      <div className="source-sample" key={`${source.source_name}-${index}`}>
        <b>{labelize(sample.category)}</b>
        <span>{sample.title || sample.reason || 'Sample record'}</span>
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 2: Add CSS**

Add to `frontend/src/styles/components.css`:

```css
.source-row__quality {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.source-row__quality span {
  min-height: 24px;
  padding: 4px 7px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--muted);
  font-size: 10px;
  text-transform: uppercase;
}

.source-row__samples {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}

.source-sample {
  display: grid;
  gap: 2px;
  padding-left: 8px;
  border-left: 2px solid rgba(255, 255, 255, 0.12);
}

.source-sample b {
  color: var(--warning);
  font-size: 10px;
  text-transform: uppercase;
}

.source-sample span {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.35;
}
```

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/workstation/RightRail.jsx frontend/src/styles/components.css
git commit -m "feat: show source diagnostics in rail"
```

---

### Task 6: Update Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/context.md`
- Modify: `docs/data-upgrade-plan.md`

- [ ] **Step 1: Update README**

Update backend test count to `155` or the actual final count from pytest, and add:

```markdown
Source quality report:

```bash
./scripts/report_source_quality.py
```

The report prints latest source run counts, rejection buckets, and bounded sample records for tuning RSS/news feeds without opening the Pi UI.
```

- [ ] **Step 2: Update context**

In `docs/context.md`, add:

```markdown
Live data tuning now persists bounded source diagnostic samples on `IngestRun`
and exposes them through `/api/v1/sources/status`, the Sources rail, and
`scripts/report_source_quality.py`. These samples are operations metadata only;
they do not create events or affect hotspots.
```

- [ ] **Step 3: Update data upgrade plan**

In `docs/data-upgrade-plan.md`, update Recommended Next Sprint:

```markdown
1. Use the Sources rail or `scripts/report_source_quality.py` after each manual
   ingest to inspect fetched/accepted/rejected counts and sample records.
2. Add or remove regional RSS feeds based on source quality samples, not just
   aggregate rejection counts.
3. Expand eval fixtures with real false positives from the Pi source samples.
4. Decide whether Bluesky should be enabled as a weak signal source.
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/context.md docs/data-upgrade-plan.md
git commit -m "docs: document live data tuning loop"
```

---

### Task 7: Full Verification

**Files:** none

- [ ] **Step 1: Run backend tests**

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: pass.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: pass. Existing Vite large-bundle warning is acceptable.

- [ ] **Step 4: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Run live local dry run**

```bash
cd backend && ../.venv/bin/python - <<'PY'
from unittest.mock import patch
from app.services.ingestion.local_news_source import LocalNewsSource
with patch('app.config.settings.local_news_enabled', True), patch('app.config.settings.local_news_fetch_articles', True), patch('app.config.settings.local_news_max_records', 50):
    source = LocalNewsSource()
    candidates = source.fetch()
    print('candidates', len(candidates))
    print('stats', source.stats)
PY
```

Expected: no `article_fetch_error` bucket from the known LAist/Texas regional pilot unless a publisher is temporarily unreachable; `sample_records` should contain bounded examples when records are rejected.

---

## Self-Review

Spec coverage:

- Live RSS tuning: Tasks 1, 3, 4, 5, 6.
- Source health/exception operations console: Tasks 2, 4, 5.
- Docs persistence for future sessions: Task 6.
- Verification before completion: Task 7.

Placeholder scan:

- No `TBD`, `TODO`, or unspecified "write tests" instructions remain.

Type consistency:

- `sample_records_json` is the DB/model field.
- `sample_records` is the API/frontend field.
- Each sample has `category`, `source_name`, `title`, `source_url`, and `reason`.

