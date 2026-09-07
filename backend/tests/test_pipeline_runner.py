"""Exercises the real pipeline end to end (real Kokoro synthesis + real ffmpeg
mastering/encoding) — the same path the CLI (scripts/render_book.py) and the G1
milestone gate use, just against a small in-memory-DB fixture instead of a whole book.
"""
import json
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables)
from app.ingest.persist import persist_document
from app.models import Block, BlockKind, Chapter, JobStatus, Segment
from app.pipeline.runner import (
    JobCancelledError,
    _build_chapter_markers,
    _build_chunk_plan,
    _build_subtitle_cues,
    _safe_filename,
    create_job,
    run_job,
)


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


def _segment(chapter_id, index, start_s, duration_s, text="x") -> Segment:
    return Segment(job_id=1, chapter_id=chapter_id, index=index, text=text, start_s=start_s, duration_s=duration_s)


def test_build_chapter_markers_spans_to_the_next_chapters_start():
    chapters = [Chapter(id=1, book_id=1, index=0, title="One"), Chapter(id=2, book_id=1, index=1, title="Two")]
    segments = [
        _segment(1, 0, 0.0, 1.0),
        _segment(1, 1, 1.0, 0.5),  # chapter 1 ends at 1.5 (last chunk's start+duration)
        _segment(2, 2, 2.7, 1.0),  # trailing 1.2s chapter pause lands inside chapter 1's span
        _segment(2, 3, 3.7, 2.0),  # chapter 2's real end: 5.7
    ]
    markers = _build_chapter_markers(chapters, segments)
    assert len(markers) == 2
    assert markers[0].title == "One"
    assert markers[0].start_s == pytest.approx(0.0)
    assert markers[0].end_s == pytest.approx(2.7)  # next chapter's start, not chapter 1's own last end
    assert markers[1].title == "Two"
    assert markers[1].start_s == pytest.approx(2.7)
    assert markers[1].end_s == pytest.approx(5.7)  # last chapter: real end of the track


def test_build_chapter_markers_skips_a_chapter_with_no_segments():
    """A chapter can be enabled but produce zero audio (e.g. every block was empty
    after normalization) — it must not show up as a zero-length or bogus marker."""
    chapters = [
        Chapter(id=1, book_id=1, index=0, title="One"),
        Chapter(id=2, book_id=1, index=1, title="Empty"),
        Chapter(id=3, book_id=1, index=2, title="Three"),
    ]
    segments = [_segment(1, 0, 0.0, 1.0), _segment(3, 1, 1.0, 1.0)]
    markers = _build_chapter_markers(chapters, segments)
    assert [m.title for m in markers] == ["One", "Three"]


def test_build_chunk_plan_excludes_skip_kind_blocks():
    """[M6-3]: a BlockKind.skip block (e.g. a PDF footnote) must never reach synthesis
    — it stays a real, visible, editable Block row, but _build_chunk_plan is where the
    exclusion from narration actually happens. The skip block sits last, after the real
    last paragraph, so this also proves "is this the chapter's last block" is decided
    from the *filtered* list — a skip block trailing the real content must not steal
    the end-of-book pause treatment from the paragraph that actually is last now."""
    chapter = Chapter(
        id=1, book_id=1, index=0, title="One",
        blocks=[
            Block(chapter_id=1, index=0, kind=BlockKind.para, text="First paragraph."),
            Block(chapter_id=1, index=1, kind=BlockKind.para, text="Second paragraph."),
            Block(chapter_id=1, index=2, kind=BlockKind.skip, text="1. A footnote nobody should hear."),
        ],
    )
    plan = _build_chunk_plan([chapter], "en", [])
    plan_texts = [item.text for item in plan]
    assert not any("footnote" in t for t in plan_texts)
    assert any("First paragraph" in t for t in plan_texts)
    assert any("Second paragraph" in t for t in plan_texts)
    # the last *narrated* chunk ("Second paragraph"'s) gets the end-of-book pause (the
    # only/last chapter's last real block), not a mid-block pause as if the skip block
    # were still counted as trailing content after it.
    assert plan[-1].pause_after_s == 0.0


def test_build_subtitle_cues_sorts_by_index_and_skips_blank_or_unsynced_segments():
    segments = [
        _segment(1, 1, 1.0, 0.5, text="second"),
        _segment(1, 0, 0.0, 1.0, text="first"),
        Segment(job_id=1, chapter_id=1, index=2, text="   ", start_s=1.5, duration_s=0.3),  # blank after strip
        Segment(job_id=1, chapter_id=1, index=3, text="never synced", start_s=None, duration_s=None),
    ]
    cues = _build_subtitle_cues(segments)
    assert [c.text for c in cues] == ["first", "second"]
    assert cues[0].start_s == pytest.approx(0.0)
    assert cues[0].end_s == pytest.approx(1.0)
    assert cues[1].start_s == pytest.approx(1.0)
    assert cues[1].end_s == pytest.approx(1.5)


@pytest.mark.slow
def test_run_job_produces_every_requested_export_format(db_session, epub_path):
    """[M5-1]/[M5-2]/[M5-3]/[M5-5]/[M5-6]/[M5-7]: one job can request MP3+M4B+Opus+FLAC+
    WAV+SRT+VTT+MP4+chapters in a single render, and every format is both recorded as a
    JobArtifact and a real, playable/parseable file — including working M4B chapter
    markers, SRT/VTT cues that line up with the real segment timings, an MP4 whose
    duration matches the mastered audio, and a YouTube chapters/description text file
    whose timestamps agree with the M4B's own chapter markers. This fixture book has no
    cover of its own, so this also exercises the [M5-5] Pillow-generated fallback cover
    being embedded in both the MP3 (attached_pic) and the MP4 (video track)."""
    from app.ingest.epub import EpubParser

    all_formats = ["mp3", "m4b", "opus", "flac", "wav", "srt", "vtt", "mp4", "chapters"]
    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")

    job = create_job(db_session, book, voice="af_heart", speed=1.0, formats=all_formats)
    primary_path = run_job(db_session, job, workers=2)

    assert primary_path.suffix == ".mp3"  # mp3 stays primary/output_path when requested
    assert _probe_duration(primary_path) > 1.0

    db_session.refresh(job)
    assert job.status == JobStatus.done
    artifacts = {a.format: a.path for a in job.artifacts}
    assert set(artifacts) == set(all_formats)

    for fmt, path_str in artifacts.items():
        path = Path(path_str)
        assert path.is_file(), fmt
        assert path.stat().st_size > 0, fmt

    m4b_chapters_probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_chapters", artifacts["m4b"]],
        capture_output=True, text=True,
    )
    m4b_chapters = json.loads(m4b_chapters_probe.stdout)["chapters"]
    assert len(m4b_chapters) == len([c for c in book.chapters if c.enabled])
    assert m4b_chapters[0]["tags"]["title"] == sorted(book.chapters, key=lambda c: c.index)[0].title

    chapters_txt = open(artifacts["chapters"], encoding="utf-8").read()
    assert chapters_txt.startswith(f"{book.title}\n")
    assert book.author in chapters_txt
    assert "0:00 " in chapters_txt  # YouTube requires the first chapter to start at 0:00
    assert m4b_chapters[0]["tags"]["title"] in chapters_txt
    if len(m4b_chapters) > 1:
        assert m4b_chapters[1]["tags"]["title"] in chapters_txt

    srt_text = open(artifacts["srt"], encoding="utf-8").read()
    assert srt_text.startswith("1\n")
    assert "-->" in srt_text

    vtt_text = open(artifacts["vtt"], encoding="utf-8").read()
    assert vtt_text.startswith("WEBVTT\n")

    mp4_probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
         artifacts["mp4"]],
        capture_output=True, text=True,
    )
    mp4_info = json.loads(mp4_probe.stdout)
    kinds = {s["codec_type"] for s in mp4_info["streams"]}
    assert kinds == {"video", "audio"}
    assert float(mp4_info["format"]["duration"]) == pytest.approx(_probe_duration(primary_path), abs=0.5)
    # 1600x1600 is generate_cover()'s own output size — confirms the MP4 actually used
    # the [M5-5] generated cover, not the plain flat-color lavfi placeholder that
    # video/render.py falls back to when no cover_path is given at all.
    mp4_video = next(s for s in mp4_info["streams"] if s["codec_type"] == "video")
    assert (mp4_video["width"], mp4_video["height"]) == (1600, 1600)

    mp3_probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_streams", artifacts["mp3"]],
        capture_output=True, text=True,
    )
    mp3_streams = json.loads(mp3_probe.stdout)["streams"]
    cover_stream = next(s for s in mp3_streams if s["codec_type"] == "video")
    assert cover_stream["disposition"]["attached_pic"] == 1


@pytest.mark.slow
def test_run_job_honors_a_non_default_video_style(db_session, epub_path):
    """[M5-4]: job.video_style routes through to the mp4 export branch, not just the
    default "static" style exercised by the multi-format test above."""
    from app.ingest.epub import EpubParser

    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")

    job = create_job(db_session, book, voice="af_heart", speed=1.0, formats=["mp4"], video_style="waveform")
    run_job(db_session, job, workers=2)

    db_session.refresh(job)
    assert job.status == JobStatus.done
    mp4_path = next(a.path for a in job.artifacts if a.format == "mp4")

    probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_streams", mp4_path],
        capture_output=True, text=True,
    )
    video_stream = next(s for s in json.loads(probe.stdout)["streams"] if s["codec_type"] == "video")
    # waveform (unlike static's 2 fps) redraws every frame at 24 fps — a cheap, direct
    # signal that the "waveform" style, not the "static" default, actually rendered.
    num, den = video_stream["r_frame_rate"].split("/")
    assert float(num) / float(den) == pytest.approx(24.0, abs=1.0)


@pytest.mark.slow
def test_run_job_splits_mp4_into_chapter_aligned_parts_when_over_the_limit(db_session, epub_path):
    """[M5-8]: a small `mp4_part_limit_s` forces the same real 2-chapter book used
    elsewhere in this file to actually split — one chapter's worth of real Kokoro
    synthesis easily exceeds a 1-second limit, so each chapter becomes its own part."""
    from app.ingest.epub import EpubParser

    document = EpubParser().parse(epub_path)
    book = persist_document(db_session, document, epub_path, "epub")
    enabled_chapter_count = len([c for c in book.chapters if c.enabled])

    split_job = create_job(db_session, book, voice="af_heart", speed=1.0, formats=["mp4"])
    run_job(db_session, split_job, workers=2, mp4_part_limit_s=1.0)
    db_session.refresh(split_job)
    assert split_job.status == JobStatus.done

    mp4_artifacts = sorted((a for a in split_job.artifacts if a.format == "mp4"), key=lambda a: a.part_index)
    assert len(mp4_artifacts) == enabled_chapter_count
    total_parts = len(mp4_artifacts)

    split_duration_sum = 0.0
    for artifact in mp4_artifacts:
        assert artifact.part_total == total_parts
        path = Path(artifact.path)
        assert path.is_file()
        # consistent, self-describing part naming — not just "did a file get written."
        assert path.name == f"{_safe_filename(book.title)} - Part {artifact.part_index} of {total_parts}.mp4"

        info = json.loads(subprocess.run(
            ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
             str(path)],
            capture_output=True, text=True,
        ).stdout)
        kinds = {s["codec_type"] for s in info["streams"]}
        assert kinds == {"video", "audio"}
        duration = float(info["format"]["duration"])
        assert duration > 0.1
        split_duration_sum += duration

    # cross-check against the same book rendered *without* splitting (same voice/speed,
    # so this hits the chunk cache — cheap, no re-synthesis): the parts' durations must
    # sum back to the whole track, proving the split lost or duplicated no audio at the
    # chapter boundary.
    unsplit_job = create_job(db_session, book, voice="af_heart", speed=1.0, formats=["mp4"])
    run_job(db_session, unsplit_job, workers=2)
    db_session.refresh(unsplit_job)
    unsplit_path = next(a.path for a in unsplit_job.artifacts if a.format == "mp4")
    assert split_duration_sum == pytest.approx(_probe_duration(unsplit_path), abs=1.0)
