"""Integration tests for the upload API, exercised through real HTTP requests against
the FastAPI app with an isolated (tmp_path) database and storage dir."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models")
    settings.ensure_dirs()

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _get_settings_override():
        return settings

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_settings] = _get_settings_override
    app.dependency_overrides[get_session] = _get_session_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_upload_epub_end_to_end(client, epub_path):
    with epub_path.open("rb") as f:
        resp = client.post("/api/books", files={"file": ("sample.epub", f, "application/epub+zip")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Sample Book"
    assert body["chapter_count"] == 2

    detail = client.get(f"/api/books/{body['id']}").json()
    assert [c["title"] for c in detail["chapters"]] == ["Chapter One", "Chapter Two"]

    chapter_id = detail["chapters"][0]["id"]
    chapter = client.get(f"/api/books/{body['id']}/chapters/{chapter_id}").json()
    assert chapter["blocks"][1]["text"] == "First paragraph."


def test_upload_txt_and_list_books(client, txt_path):
    with txt_path.open("rb") as f:
        resp = client.post("/api/books", files={"file": ("sample.txt", f, "text/plain")})
    assert resp.status_code == 201, resp.text

    books = client.get("/api/books").json()
    assert len(books) == 1
    assert books[0]["source_format"] == "txt"
    assert books[0]["language"] == "en"  # detected, since TXT never knows its own language


def test_upload_unavailable_calibre_format_returns_422(client, tmp_path):
    path = tmp_path / "sample.mobi"
    path.write_bytes(b"not a real mobi container")
    with path.open("rb") as f:
        resp = client.post("/api/books", files={"file": ("sample.mobi", f, "application/x-mobipocket-ebook")})
    assert resp.status_code == 422
    assert "Calibre" in resp.json()["detail"]


def test_get_nonexistent_book_returns_404(client):
    resp = client.get("/api/books/999")
    assert resp.status_code == 404


def test_formats_endpoint_reports_calibre_unavailable(client):
    formats = client.get("/api/formats").json()
    mobi = next(f for f in formats if f["extension"] == "mobi")
    assert mobi["available"] is False
    assert "Calibre" in mobi["note"]
