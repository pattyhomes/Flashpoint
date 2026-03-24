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


settings = Settings()
