#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "Error: .env file not found."
    echo "Run: cp .env.example .env"
    exit 1
fi

cd "$REPO_ROOT/backend"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
