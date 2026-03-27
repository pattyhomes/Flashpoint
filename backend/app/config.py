from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from repo root regardless of CWD (backend/ when running uvicorn).
# __file__ = REPO_ROOT/backend/app/config.py → .parent×3 = REPO_ROOT
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = True

    database_url: str = "sqlite:///../data/flashpoint.db"

    ingestion_interval_seconds: int = 1800
    mock_data_enabled: bool = True
    ingest_source: str = "mock"  # "mock" | "gdelt"

    # Event Registry — supplementary source for corroboration and selective discovery
    event_registry_enabled: bool = False
    event_registry_api_key: str = ""
    event_registry_interval_seconds: int = 1800
    event_registry_lookback_hours: int = 6
    event_registry_max_records: int = 100
    event_registry_us_only: bool = True
    event_registry_min_classification_score: float = 0.6
    event_registry_min_location_precision: str = "city"   # "venue" | "city" | "state"
    event_registry_create_new_events: bool = False
    event_registry_max_new_events_per_run: int = 10
    event_registry_max_confidence_uncorroborated: float = 0.58


settings = Settings()
