#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT/backend"
python -c "from app.jobs.seed import run_mock_ingestion; run_mock_ingestion()"
