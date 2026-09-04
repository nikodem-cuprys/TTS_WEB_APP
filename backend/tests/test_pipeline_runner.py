"""Exercises the real pipeline end to end (real Kokoro synthesis + real ffmpeg
mastering/encoding) — the same path the CLI (scripts/render_book.py) and the G1
milestone gate use, just against a small in-memory-DB fixture instead of a whole book.
"""
import json
import subprocess

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.ingest.persist import persist_document
from app.models import JobStatus
from app.pipeline.runner import JobCancelledError, create_job, run_job


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # Pool workers are separate spawned processes — only an env var survives spawn,
    # a monkeypatched get_settings() in this process would not reach them. But
    # get_settings() is also @lru_cache'd, so if an earlier test in the same pytest
    # session already called it (app.main does, at import time) with the real paths,
    # this process's *own* calls (run_job() reads settings directly, unlike the pool)
    # would keep returning that stale cache despite the env var — clear it explicitly,
    # both now and on teardown so later tests get the real settings back.
    from app.config import get_settings

    monkeypatch.setenv("AUDIOBOOK_DATA_DIR", str(tmp_path / "data"))
    for sub in ("cache", "output", "books"):
        (tmp_path / "data" / sub).mkdir(parents=True, exist_ok=True)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _probe_duration(path) -> float:
    result = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


@pytest.mark.slow
def test_run_job_end_to_end(db_session, epub_path):
    from app.ingest.epub import EpubParser

    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")

    job = create_job(db_session, book, voice="af_heart", speed=1.0)
    output_path = run_job(db_session, job, workers=2)

    assert output_path.is_file()
    assert output_path.suffix == ".mp3"
    assert _probe_duration(output_path) > 1.0

    db_session.refresh(job)
    assert job.status == JobStatus.done
    assert job.finished_at is not None

    stages = {s.name: s for s in job.stages}
    assert set(stages) == {"prepare", "synthesize", "assemble", "master", "export"}
    assert all(s.status == JobStatus.done for s in stages.values())

    segments = sorted(job.segments, key=lambda s: s.index)
    assert len(segments) > 0
    assert all(s.status == JobStatus.done for s in segments)
    assert all(s.duration_s is not None and s.duration_s > 0 for s in segments)
    assert all(s.start_s is not None for s in segments)
    # timings are monotonically non-decreasing across the assembled track
    assert all(b.start_s >= a.start_s for a, b in zip(segments, segments[1:]))


def test_run_job_stops_at_the_next_checkpoint_when_already_cancelled(db_session, epub_path):
    """A cancel request lands via a different DB session/connection (the API handler
    for POST /api/jobs/{id}/cancel) — simulate that here by flipping the status on the
    job row directly rather than going through run_job, then confirm run_job notices
    on its very first cancellation checkpoint (before the "prepare" stage) and never
    starts synthesizing."""
    from app.ingest.epub import EpubParser

    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")
    job = create_job(db_session, book, voice="af_heart", speed=1.0)

    job.status = JobStatus.cancelled
    db_session.add(job)
    db_session.commit()

    with pytest.raises(JobCancelledError):
        run_job(db_session, job, workers=2)

    db_session.refresh(job)
    assert job.status == JobStatus.cancelled
    assert job.finished_at is not None
    assert job.stages == []  # cancelled before any stage even started
