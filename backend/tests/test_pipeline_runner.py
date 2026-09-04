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


def _make_epub(tmp_path, language: str, title: str, chapter_title: str, paragraphs: list[str]):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"test-{language}")
    book.set_title(title)
    book.set_language(language)

    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    chapter = epub.EpubHtml(title=chapter_title, file_name="chap1.xhtml", lang=language)
    chapter.content = f"<html><body><h1>{chapter_title}</h1>{body}</body></html>"
    book.add_item(chapter)
    book.toc = (epub.Link("chap1.xhtml", chapter_title, "c1"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    path = tmp_path / f"sample_{language}.epub"
    epub.write_epub(str(path), book)
    return path


@pytest.mark.slow
@pytest.mark.parametrize(
    "language,voice,title,chapter_title,paragraphs",
    [
        (
            "pl", "pl_PL-gosia-medium", "Polska Książka", "Rozdział pierwszy",
            ["To wydarzyło się w 1939 roku.", "Kosztowało to 100 zł."],
        ),
        (
            "de", "de_DE-thorsten-high", "Deutsches Buch", "Kapitel eins",
            ["Das geschah im Jahr 1939.", "Es kostete 5 Euro."],
        ),
        (
            "zh", "zf_xiaobei", "中文书", "第一章",
            ["这发生在1939年。", "这花了100元。"],
        ),
    ],
)
def test_run_job_end_to_end_multilingual(
    db_session, tmp_path, language, voice, title, chapter_title, paragraphs
):
    """The M2 gate proved the pipeline works for English; this is the same proof for
    the three languages M4 added — real normalizer, real engine (Piper for pl/de,
    Kokoro+misaki for zh), real ffmpeg mastering, not just the per-module unit tests."""
    from app.ingest.epub import EpubParser

    epub_path = _make_epub(tmp_path, language, title, chapter_title, paragraphs)
    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")
    assert book.language == language

    job = create_job(db_session, book, voice=voice, speed=1.0)
    output_path = run_job(db_session, job, workers=2)

    assert output_path.is_file()
    assert _probe_duration(output_path) > 1.0

    db_session.refresh(job)
    assert job.status == JobStatus.done
    assert all(s.status == JobStatus.done for s in job.stages)
    assert all(s.status == JobStatus.done for s in job.segments)


@pytest.mark.slow
def test_lexicon_edit_invalidates_only_the_chunks_it_affects(db_session, tmp_path):
    """The core [M4-6] promise: editing one lexicon entry should only force
    re-synthesis of chunks whose text actually contains the pattern — a chunk
    untouched by the edit must come out of the *same* cache entry both times."""
    from app.ingest.epub import EpubParser
    from app.models import LexiconEntry

    epub_path = _make_epub(
        tmp_path, "en", "Fantasy Book", "Chapter One",
        ["Zaltharion walked into the room.", "The weather was pleasant that day."],
    )
    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")

    job1 = create_job(db_session, book, voice="af_heart", speed=1.0)
    run_job(db_session, job1, workers=2)
    db_session.refresh(job1)
    # keyed by the ORIGINAL (pre-lexicon) text, since that's what's stable to look up
    # by across both runs — the affected chunk's own text changes between runs.
    by_text1 = {s.text: s for s in job1.segments}
    heading = by_text1["Chapter One"]
    affected = by_text1["Zaltharion walked into the room."]
    unaffected = by_text1["The weather was pleasant that day."]

    entry = LexiconEntry(book_id=book.id, pattern="Zaltharion", replacement="Zal-thar-ee-on")
    db_session.add(entry)
    db_session.commit()

    job2 = create_job(db_session, book, voice="af_heart", speed=1.0)
    run_job(db_session, job2, workers=2)
    db_session.refresh(job2)
    by_text2 = {s.text: s for s in job2.segments}
    heading2 = by_text2["Chapter One"]
    affected2 = by_text2["Zal-thar-ee-on walked into the room."]
    unaffected2 = by_text2["The weather was pleasant that day."]

    assert affected.cache_key != affected2.cache_key, "the edited chunk must get a new cache key"
    assert unaffected.cache_key == unaffected2.cache_key, "the unrelated chunk must reuse its cache entry"
    assert heading.cache_key == heading2.cache_key, "an unrelated heading must also reuse its cache entry"

    # and the underlying cached files are literally the same file for untouched chunks
    assert unaffected.audio_path == unaffected2.audio_path
    assert heading.audio_path == heading2.audio_path
    assert affected.audio_path != affected2.audio_path


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
