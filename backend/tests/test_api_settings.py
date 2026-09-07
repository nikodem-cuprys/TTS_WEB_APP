import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    monkeypatch.setenv("AUDIOBOOK_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = lambda: (yield Session(engine))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def test_get_settings_returns_defaults(client):
    body = client.get("/api/settings").json()
    assert body["tts_workers"] == 4
    assert body["loudness_target_i"] == -19.0
    assert body["loudness_target_tp"] == -3.0
    assert body["loudness_target_lra"] == 7.0
    assert body["mp4_part_limit_s"] == 11 * 3600 + 45 * 60
    assert body["output_dir"]
    assert body["models_dir"]


def test_put_settings_updates_and_persists(client):
    resp = client.put("/api/settings", json={"tts_workers": 8, "loudness_target_i": -16.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tts_workers"] == 8
    assert body["loudness_target_i"] == -16.0
    assert body["loudness_target_tp"] == -3.0  # untouched field keeps its value

    # persisted, not just returned in the response
    again = client.get("/api/settings").json()
    assert again["tts_workers"] == 8
    assert again["loudness_target_i"] == -16.0


def test_put_settings_rejects_invalid_worker_count(client):
    resp = client.put("/api/settings", json={"tts_workers": 0})
    assert resp.status_code == 422


def test_put_settings_updates_mp4_part_limit(client):
    resp = client.put("/api/settings", json={"mp4_part_limit_s": 3600.0})
    assert resp.status_code == 200
    assert resp.json()["mp4_part_limit_s"] == 3600.0
    assert client.get("/api/settings").json()["mp4_part_limit_s"] == 3600.0


def test_put_settings_rejects_non_positive_mp4_part_limit(client):
    resp = client.put("/api/settings", json={"mp4_part_limit_s": 0})
    assert resp.status_code == 422


def test_disk_usage_reports_real_numbers(client):
    body = client.get("/api/settings/disk-usage").json()
    assert body["cache_bytes"] >= 0
    assert body["output_bytes"] >= 0
    assert body["models_bytes"] > 0  # real downloaded models are present
    assert body["free_bytes"] > 0


def test_model_status_reflects_real_downloaded_models(client):
    statuses = client.get("/api/settings/models").json()
    assert len(statuses) == 8
    assert all(s["present"] for s in statuses)  # all models were downloaded in M0
