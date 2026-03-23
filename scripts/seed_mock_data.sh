#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT/backend"
python3 -c "from app.jobs.seed import reset_and_seed; reset_and_seed()"
