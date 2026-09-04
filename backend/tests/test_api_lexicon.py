import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models")
    settings.ensure_dirs()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = lambda: (yield Session(engine))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def uploaded_book_id(client, epub_path):
    with epub_path.open("rb") as f:
        resp = client.post("/api/books", files={"file": ("sample.epub", f, "application/epub+zip")})
    return resp.json()["id"]


def test_create_and_list_lexicon_entries(client, uploaded_book_id):
    resp = client.post(
        f"/api/books/{uploaded_book_id}/lexicon",
        json={"pattern": "Cthulhu", "replacement": "kuh-THU-loo"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pattern"] == "Cthulhu"
    assert body["is_regex"] is False
    assert body["enabled"] is True

    listed = client.get(f"/api/books/{uploaded_book_id}/lexicon").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_update_lexicon_entry(client, uploaded_book_id):
    entry = client.post(
        f"/api/books/{uploaded_book_id}/lexicon", json={"pattern": "X", "replacement": "Y"}
    ).json()

    resp = client.patch(
        f"/api/books/{uploaded_book_id}/lexicon/{entry['id']}", json={"replacement": "Z", "enabled": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pattern"] == "X"  # untouched field
    assert body["replacement"] == "Z"
    assert body["enabled"] is False


def test_delete_lexicon_entry(client, uploaded_book_id):
    entry = client.post(
        f"/api/books/{uploaded_book_id}/lexicon", json={"pattern": "X", "replacement": "Y"}
    ).json()

    resp = client.delete(f"/api/books/{uploaded_book_id}/lexicon/{entry['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/books/{uploaded_book_id}/lexicon").json() == []


def test_invalid_regex_pattern_rejected(client, uploaded_book_id):
    resp = client.post(
        f"/api/books/{uploaded_book_id}/lexicon",
        json={"pattern": "[unclosed", "replacement": "x", "is_regex": True},
    )
    assert resp.status_code == 422


def test_literal_pattern_not_validated_as_regex(client, uploaded_book_id):
    # "[unclosed" is invalid regex syntax but perfectly fine as a literal string.
    resp = client.post(
        f"/api/books/{uploaded_book_id}/lexicon",
        json={"pattern": "[unclosed", "replacement": "x", "is_regex": False},
    )
    assert resp.status_code == 201


def test_lexicon_entry_not_found(client, uploaded_book_id):
    assert client.patch(f"/api/books/{uploaded_book_id}/lexicon/999", json={"pattern": "x"}).status_code == 404
    assert client.delete(f"/api/books/{uploaded_book_id}/lexicon/999").status_code == 404


def test_lexicon_for_missing_book_returns_404(client):
    resp = client.get("/api/books/999/lexicon")
    assert resp.status_code == 404
