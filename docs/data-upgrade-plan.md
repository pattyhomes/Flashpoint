# Data Upgrade Plan

This doc preserves the intelligence/data roadmap across agent sessions.

## Current Baseline

Stage 1 evidence-first infrastructure is implemented on SQLite:

- `EvidenceItem` stores source snapshots and provenance.
- `Observation` stores leads, context, linked evidence, promoted records, and
  dismissed records.
- Existing `Event`, `EventSource`, and `Hotspot` tables remain the confirmed
  layer.
- Observation APIs exist for listing, promoting, dismissing, linking, and map
  signals.
- GDELT and Event Registry create evidence/observations alongside confirmed
  event workflows.
- NWS, Bluesky, Mastodon, and ACLED adapters exist behind config.
- Ollama embeddings are optional and fail soft.
- V3 UI has Sources/Leads and map signal surfaces.

## Core Intelligence Rules

- Sources create evidence and observations first.
- Only confirmed/promoted events affect hotspots and priority scoring.
- Weak social/open-web leads never auto-create confirmed map events.
- Social volume can render as amber signal heat only.
- NWS/context observations remain operator context and do not inflate unrest
  scores.
- Corroboration requires independent source families, not syndicated copies.
- Uncorroborated observations keep capped confidence.
- Dismissed evidence should remain dismissed if reingested.

## Stage 1.5: Make The Data Real

Goal: improve live data quality without moving to Postgres yet.

### 1. Scheduled Source Configuration

- Turn on real schedules for selected observation sources.
- Keep GDELT/Event Registry as the confirmed/news backbone.
- Add NWS as context observations.
- Add Bluesky/Mastodon as weak signal feeds only.
- Enable ACLED only when credentials/access are available.
- Add operator-visible source freshness and failure states.

### 2. Geocoding and Location Confidence

This is the highest-leverage data upgrade.

- Add a local geocoding/cache layer.
- Normalize city/county/state/venue names.
- Track location confidence and precision separately from event confidence.
- Store why a location was chosen.
- Prevent weak or random geography from becoming map signals or hotspots.

Likely SQLite-first tables:

- `location_cache`
- `location_aliases`
- optional `observation_location_candidates`

### 3. Source Health and Exceptions

Make the Sources rail a real operations console:

- feed stale/failed/noisy states
- lead exception categories
- last successful fetch per source
- records fetched vs accepted vs rejected
- reasons leads stayed unpromoted

Candidate exception categories:

- bad location
- low confidence
- social only
- syndicated duplicate
- context only
- possible duplicate
- needs operator review

### 4. Semantic Duplicate Detection

Use optional local embeddings where useful:

- cache embeddings in `EvidenceItem.embedding_json` or a future side table
- use semantic similarity for candidate duplicate/link detection
- never require Ollama for ingestion to succeed
- keep concurrency low and outputs cached

This should improve linking and noise control, not generate unattended prose.

### 5. Evaluation Dataset

Create a small reference dataset before tuning thresholds:

- true positives: known unrest events
- false positives: weather, sports, traffic, crime-only, generic politics
- duplicate/syndicated clusters
- bad-location examples
- social-only rumor examples

Score:

- false event creation
- missed event
- bad link
- bad location
- noisy hotspot contribution
- correct exception classification

## Stage 2: Durable Backend

Move when SQLite and in-process jobs become the bottleneck:

- Postgres + PostGIS
- worker queue for ingestion/enrichment/scoring
- source registry tables
- durable job artifacts
- better spatial/time indexes
- richer search and evidence archive
- merge/split/timeline workflows

## Stage 3: Serious Intelligence

After real data quality and durable backend exist:

- incident timelines with citations
- "why this hotspot matters" explanations
- anomaly detection against regional baselines
- confidence-calibrated summaries
- forecast/risk indicators
- analyst feedback loop for threshold tuning
- optional local or server-side generation with strict caching and provenance

## Recommended Next Sprint

Before Stage 1.5 implementation begins:

1. Confirm which live feeds should be enabled on the Pi.
2. Define location-confidence fields and SQLite migration.
3. Build source health telemetry and exception categories.
4. Add a tiny eval fixture set for data-quality regression tests.
