"""Integration tests for the render-job API: creation kicks off a real background
render (real Kokoro synthesis + ffmpeg), progress is polled through GET /api/jobs/{id}
(a light SSE smoke test covers the streaming path separately), and cancellation is
exercised through the real endpoint rather than by calling into the pipeline directly.
"""
import time

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.api import jobs as jobs_api
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app

POLL_TIMEOUT_S = 60
POLL_INTERVAL_S = 0.3


@pytest.fixture
def client(tmp_path, monkeypatch):
    # models_dir deliberately left at its default (the real downloaded models) — only
    # the data dir (books/cache/output/db) needs isolating for a clean test.
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _get_settings_override():
        return settings

    def _get_session_override():
        with Session(engine) as session:
            yield session

    # The background render thread (app.api.jobs._run_in_background) doesn't go
    # through FastAPI's dependency injection — it calls db.new_session() directly, a
    # name bound into app.api.jobs's own module namespace at import time. Overriding
    # app.dependency_overrides only affects request-time Depends(), so the thread
    # needs its session source patched separately to see the same isolated DB.
    monkeypatch.setattr(jobs_api, "new_session", lambda: Session(engine))
    # get_settings() is @lru_cache'd process-wide; the background thread runs in this
    # same process (a plain Thread, unlike the pool's separate spawned processes), so
    # an env var alone wouldn't override an already-cached instance — clear it too.
    monkeypatch.setenv("AUDIOBOOK_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    app.dependency_overrides[get_settings] = _get_settings_override
    app.dependency_overrides[get_session] = _get_session_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


@pytest.fixture
def uploaded_book_id(client, epub_path):
    with epub_path.open("rb") as f:
        resp = client.post("/api/books", files={"file": ("sample.epub", f, "application/epub+zip")})
    assert resp.status_code == 201
    return resp.json()["id"]


def _poll_until_terminal(client, job_id, timeout_s=POLL_TIMEOUT_S):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"job {job_id} did not reach a terminal state within {timeout_s}s")


@pytest.mark.slow
def test_create_job_renders_and_downloads(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart", "speed": 1.0})
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] in ("queued", "running")

    final = _poll_until_terminal(client, job["id"])
    assert final["status"] == "done", final
    assert {s["name"] for s in final["stages"]} == {"prepare", "synthesize", "assemble", "master", "export"}
    assert all(s["status"] == "done" for s in final["stages"])

    download = client.get(f"/api/jobs/{job['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "audio/mpeg"
    assert len(download.content) > 1000
    # a real save dialog needs a filename — that's what tells the browser to save
    # rather than try to play it, which is exactly why /stream (below) must NOT have this.
    assert "attachment" in download.headers["content-disposition"]

    # regression: an <audio> element's src pointed at /download never showed a
    # duration or allowed seeking in real browser testing, because FileResponse's
    # filename= argument sets Content-Disposition: attachment, which tells the
    # browser this is a file to save, not inline media to play.
    stream = client.get(f"/api/jobs/{job['id']}/stream")
    assert stream.status_code == 200
    assert stream.headers["content-type"] == "audio/mpeg"
    assert "content-disposition" not in stream.headers
    assert stream.content == download.content

    # regression: SQLite round-trips datetime columns as naive, and a bare
    # .isoformat() on that produced no UTC offset — which JS's Date parser then
    # misread as local time, making every "elapsed" display wrong by the viewer's
    # UTC offset (confirmed as a ~7000s error in real browser testing).
    for field in ("created_at", "started_at", "finished_at"):
        assert final[field].endswith("+00:00"), f"{field}={final[field]!r} has no UTC offset"


@pytest.mark.slow
def test_cancel_job_reaches_cancelled_status(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_bella", "speed": 1.0})
    job_id = resp.json()["id"]

    cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200

    final = _poll_until_terminal(client, job_id)
    assert final["status"] == "cancelled"

    # cancelling a job already in a terminal state is a no-op, not an error
    again = client.post(f"/api/jobs/{job_id}/cancel")
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


@pytest.mark.slow
def test_job_events_stream_sends_updates_and_closes(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart", "speed": 1.0})
    job_id = resp.json()["id"]

    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events", timeout=POLL_TIMEOUT_S) as stream:
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(line)
            if len(events) >= 1 and '"status":"done"' in events[-1]:
                break
            if len(events) >= 1 and '"status":"failed"' in events[-1]:
                break

    assert events, "expected at least one SSE data event"
    assert '"status":"done"' in events[-1]


def test_create_job_for_missing_book_returns_404(client):
    resp = client.post("/api/books/999/jobs", json={"voice": "af_heart"})
    assert resp.status_code == 404


def test_create_job_with_unknown_voice_returns_422(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "not-a-real-voice"})
    assert resp.status_code == 422


def test_create_job_with_wrong_engine_voice_returns_422(client, uploaded_book_id):
    # The book is English (routes to kokoro); a Piper (Polish/German) voice must be
    # rejected up front rather than silently reaching the wrong engine's worker and
    # failing deep inside the synthesize stage instead.
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "pl_PL-gosia-medium"})
    assert resp.status_code == 422
    assert "piper" in resp.json()["detail"]
    assert "kokoro" in resp.json()["detail"]


def test_create_job_with_unsupported_format_returns_422(client, uploaded_book_id):
    resp = client.post(
        f"/api/books/{uploaded_book_id}/jobs",
        json={"voice": "af_heart", "formats": ["mp3", "not-a-real-format"]},
    )
    assert resp.status_code == 422
    assert "not-a-real-format" in resp.json()["detail"]


def test_create_job_with_empty_formats_returns_422(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart", "formats": []})
    assert resp.status_code == 422


def test_create_job_with_unsupported_video_style_returns_422(client, uploaded_book_id):
    resp = client.post(
        f"/api/books/{uploaded_book_id}/jobs",
        json={"voice": "af_heart", "formats": ["mp4"], "video_style": "not-a-real-style"},
    )
    assert resp.status_code == 422
    assert "not-a-real-style" in resp.json()["detail"]


def test_create_job_defaults_video_style_to_static(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart"})
    assert resp.json()["video_style"] == "static"
    client.post(f"/api/jobs/{resp.json()['id']}/cancel")  # don't leave a render running past the test


def test_download_unproduced_artifact_format_returns_404(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart"})
    job_id = resp.json()["id"]
    download = client.get(f"/api/jobs/{job_id}/artifacts/m4b/download")
    assert download.status_code == 404
    client.post(f"/api/jobs/{job_id}/cancel")  # don't leave a render running past the test


def test_download_before_job_finishes_returns_409(client, uploaded_book_id):
    resp = client.post(f"/api/books/{uploaded_book_id}/jobs", json={"voice": "af_heart"})
    job_id = resp.json()["id"]
    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 409
    client.post(f"/api/jobs/{job_id}/cancel")  # don't leave a render running past the test


def test_get_nonexistent_job_returns_404(client):
    assert client.get("/api/jobs/999").status_code == 404
