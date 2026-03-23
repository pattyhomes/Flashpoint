# Flashpoint

Local-first U.S. intelligence dashboard. Tracks unrest, protests, and civil disruptions in real time.

## Stack

- **Backend:** FastAPI + SQLite (SQLAlchemy)
- **Frontend:** _(coming soon)_
- **Target platform:** Mac Mini (dev) → Raspberry Pi 5 (deployment)

## Quick Start

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e .

# 3. Set up environment variables
cp .env.example .env

# 4. Start the backend
bash scripts/dev_backend.sh
```

- Health check: http://localhost:8000/api/v1/health
- API docs: http://localhost:8000/docs

## Seed mock data

```bash
bash scripts/seed_mock_data.sh
```
