import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401  (registers tables)
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine

    settings = Settings(data_dir=tmp_path / "data")  # models_dir stays at the real downloaded models
    settings.ensure_dirs()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    # registry.get_engine()/pipeline.cache call the module-level get_settings()
    # directly (not via Depends), and it's @lru_cache'd process-wide — clear it so
    # this test's data_dir override actually takes effect instead of a stale real-path
    # instance left cached by an earlier test module.
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


def test_list_voices_includes_all_routed_engines(client):
    # 54 Kokoro (en/zh routed, plus a handful of other languages it just happens to
    # catalog) + 3 Piper (pl/de routed) — see registry.py's LANGUAGE_ROUTING ([M4-5]).
    voices = client.get("/api/voices").json()
    assert len(voices) == 57

    en_voices = [v for v in voices if v["language"] == "en"]
    assert any(v["id"] == "af_heart" for v in en_voices)
    assert all(v["engine"] == "kokoro" and v["sample_rate"] == 24000 for v in en_voices)

    pl_voices = [v for v in voices if v["language"] == "pl"]
    assert len(pl_voices) == 2
    assert all(v["engine"] == "piper" and v["sample_rate"] == 22050 for v in pl_voices)

    de_voices = [v for v in voices if v["language"] == "de"]
    assert len(de_voices) == 1
    assert de_voices[0]["engine"] == "piper"

    zh_voices = [v for v in voices if v["language"] == "zh"]
    assert len(zh_voices) == 8
    assert all(v["engine"] == "kokoro" for v in zh_voices)


def test_unknown_voice_preview_returns_404(client):
    resp = client.post("/api/voices/not-a-real-voice/preview")
    assert resp.status_code == 404


@pytest.mark.slow
def test_preview_synthesizes_and_caches(client):
    first = client.post("/api/voices/af_heart/preview")
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert len(first.content) > 1000

    second = client.post("/api/voices/af_heart/preview")
    assert second.status_code == 200
    assert second.content == first.content  # same cached bytes both times
