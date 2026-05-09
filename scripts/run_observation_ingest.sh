#!/bin/bash
set -euo pipefail

SOURCE="${1:-}"
case "$SOURCE" in
  nws|bluesky|mastodon|local_news|acled) ;;
  *)
    echo "Usage: bash scripts/run_observation_ingest.sh {nws|bluesky|mastodon|local_news|acled}" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/backend"
"$REPO_ROOT/.venv/bin/python" -c "from app.main import _migrate; from app.jobs.seed import run_observation_source_ingestion; _migrate(); run_observation_source_ingestion('$SOURCE')"
