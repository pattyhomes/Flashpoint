from pathlib import Path

from app.database import _resolve_database_url


def test_legacy_parent_data_sqlite_url_resolves_inside_repo_data_dir():
    resolved = _resolve_database_url("sqlite:///../data/flashpoint.db")
    expected = Path(__file__).resolve().parents[2] / "data" / "flashpoint.db"

    assert resolved == f"sqlite:///{expected}"


def test_relative_sqlite_url_resolves_from_repo_root():
    resolved = _resolve_database_url("sqlite:///./data/flashpoint.db")
    expected = Path(__file__).resolve().parents[2] / "data" / "flashpoint.db"

    assert resolved == f"sqlite:///{expected}"
