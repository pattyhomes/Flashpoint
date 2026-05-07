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

    # Stage 1 observation sources — disabled by default; these feed the review queue.
    nws_alerts_enabled: bool = False
    nws_alerts_area: str = ""  # empty = all active alerts; otherwise state/region code, e.g. "PA"
    nws_alerts_interval_seconds: int = 1800

    bluesky_enabled: bool = False
    bluesky_query: str = "protest OR demonstration"
    bluesky_max_records: int = 25
    bluesky_interval_seconds: int = 1800

    mastodon_enabled: bool = False
    mastodon_instance_url: str = "https://mastodon.social"
    mastodon_access_token: str = ""
    mastodon_query: str = "protest"
    mastodon_max_records: int = 25
    mastodon_interval_seconds: int = 1800

    acled_enabled: bool = False
    acled_api_url: str = "https://api.acleddata.com/acled/read"
    acled_api_key: str = ""
    acled_email: str = ""
    acled_lookback_days: int = 7
    acled_max_records: int = 50
    acled_interval_seconds: int = 3600

    # Local AI enrichment — safe by default: opt-in, bounded, and nullable.
    ollama_embeddings_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "all-minilm"


settings = Settings()
