"""Orchestrates the full book -> audiobook pipeline: normalize -> segment -> synthesize
(cached, pooled) -> assemble -> master -> export. Writes Job/JobStage/Segment rows to
SQLite as it goes. See PLAN.md 'pipeline/runner.py'.

"Resume from cache" isn't a separate code path — it falls out of the design for free.
Every chunk's cache key is a deterministic hash of its exact inputs (pipeline/cache.py),
and the worker pool always checks the cache before synthesizing (tts/pool.py), so
re-running the same book/voice/speed after an interruption or a partial failure just
re-uses whatever was already rendered and only synthesizes what's missing.

Live per-chunk progress (SSE) is a GUI concern that lands in [M3-5]; this reports
coarse stage-level progress only, which is enough for the M2 CLI gate.
"""
import re
import time
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf
from sqlmodel import Session

from ..audio.assemble import (
    PAUSE_CHAPTER_S,
    PAUSE_PARAGRAPH_S,
    PAUSE_SENTENCE_S,
    AssembleItem,
    assemble_chapter,
)
from ..audio.encode import encode_mp3, write_wav
from ..audio.loudness import normalize_loudness
from ..config import get_settings
from ..models import Book, Job, JobStage, JobStatus, Segment
from ..pipeline import cache
from ..text.normalize import get_version as normalizer_version
from ..text.normalize import normalize
from ..text.segment import segment_text
from ..tts.pool import DEFAULT_WORKERS, SynthPool, SynthRequest
from ..tts.registry import engine_for_language

STAGE_NAMES = ["prepare", "synthesize", "assemble", "master", "export"]
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]+")


class PipelineError(Exception):
    pass


@dataclass
class _ChunkPlan:
    chapter_id: int
    text: str
    pause_after_s: float


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name).strip() or "book"


def _build_chunk_plan(chapters: list, language: str) -> list[_ChunkPlan]:
    """Flattens every enabled chapter's blocks into an ordered chunk plan, deciding
    each chunk's trailing pause from its position: mid-block chunks get the shortest
    (sentence) pause, a block's last chunk gets the paragraph pause unless it's also
    its chapter's last block (chapter pause), and the very last chunk of the book gets
    none. Never crosses a block boundary within one segment_text() call — see
    text/segment.py's docstring on why that matters for this pause logic."""
    plan: list[_ChunkPlan] = []
    for chapter_i, chapter in enumerate(chapters):
        is_last_chapter = chapter_i == len(chapters) - 1
        blocks = sorted(chapter.blocks, key=lambda b: b.index)
        for block_i, block in enumerate(blocks):
            is_last_block = block_i == len(blocks) - 1
            normalized = normalize(block.text, language)
            chunks = segment_text(normalized, language)
            for chunk_i, chunk_text in enumerate(chunks):
                is_last_chunk = chunk_i == len(chunks) - 1
                if not is_last_chunk:
                    pause = PAUSE_SENTENCE_S
                elif not is_last_block:
                    pause = PAUSE_PARAGRAPH_S
                elif not is_last_chapter:
                    pause = PAUSE_CHAPTER_S
                else:
                    pause = 0.0
                plan.append(_ChunkPlan(chapter_id=chapter.id, text=chunk_text, pause_after_s=pause))
    return plan


def time_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _start_stage(session: Session, job: Job, name: str) -> JobStage:
    stage = JobStage(job_id=job.id, name=name, status=JobStatus.running, started_at=time_now())
    session.add(stage)
    session.commit()
    session.refresh(stage)
    return stage


def _finish_stage(session: Session, stage: JobStage, status: JobStatus = JobStatus.done) -> None:
    stage.status = status
    stage.progress = 1.0
    stage.finished_at = time_now()
    session.add(stage)
    session.commit()


def create_job(session: Session, book: Book, *, voice: str, speed: float = 1.0, engine_id: str = "kokoro") -> Job:
    job = Job(book_id=book.id, status=JobStatus.queued, voice=voice, engine=engine_id, speed=speed, formats="mp3")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def run_job(session: Session, job: Job, *, workers: int = DEFAULT_WORKERS, output_path: Path | None = None) -> Path:
    settings = get_settings()
    book = session.get(Book, job.book_id)
    if book is None:
        raise PipelineError(f"job {job.id} references a missing book {job.book_id}")

    job.status = JobStatus.running
    job.started_at = time_now()
    session.add(job)
    session.commit()

    try:
        # --- prepare: normalize + segment + persist Segment rows -------------------
        stage = _start_stage(session, job, "prepare")
        engine = engine_for_language(book.language)
        chapters = sorted([c for c in book.chapters if c.enabled], key=lambda c: c.index)
        if not chapters:
            raise PipelineError(f"book {book.id} has no enabled chapters")

        plan = _build_chunk_plan(chapters, book.language)
        norm_version = normalizer_version(book.language)

        segments: list[Segment] = []
        requests: list[SynthRequest] = []
        for i, item in enumerate(plan):
            key = cache.compute_key(
                text=item.text, voice=job.voice, engine_id=engine.id,
                engine_version=engine.version, speed=job.speed, normalizer_version=norm_version,
            )
            segments.append(
                Segment(
                    job_id=job.id, chapter_id=item.chapter_id, index=i, text=item.text,
                    cache_key=key, status=JobStatus.queued,
                )
            )
            requests.append(
                SynthRequest(key=key, text=item.text, voice=job.voice, engine_id=engine.id, speed=job.speed)
            )
        session.add_all(segments)
        session.commit()
        _finish_stage(session, stage)

        # --- synthesize --------------------------------------------------------------
        stage = _start_stage(session, job, "synthesize")
        with SynthPool(workers=workers) as pool:
            results = pool.synth_many(requests)

        failed = [r for r in results if r.error]
        for segment, result in zip(segments, results):
            segment.status = JobStatus.failed if result.error else JobStatus.done
            segment.audio_path = None if result.error else str(cache.cache_path(result.key))
            segment.duration_s = None if result.error else result.duration_s
            session.add(segment)
        session.commit()

        if failed:
            _finish_stage(session, stage, status=JobStatus.failed)
            raise PipelineError(f"{len(failed)} chunk(s) failed to synthesize: {failed[0].error}")
        _finish_stage(session, stage)

        # --- assemble: concatenate every chunk with fades + pauses -------------------
        stage = _start_stage(session, job, "assemble")
        assemble_items = []
        for item, segment in zip(plan, segments):
            samples, sr = sf.read(segment.audio_path, dtype="float32")
            assemble_items.append(AssembleItem(samples=samples, sample_rate=sr, pause_after_s=item.pause_after_s))

        assembled, sample_rate, timings = assemble_chapter(assemble_items)
        for segment, timing in zip(segments, timings):
            segment.start_s = timing.start_s
            segment.duration_s = timing.duration_s
            session.add(segment)
        session.commit()

        raw_wav = write_wav(settings.cache_dir() / f"job_{job.id}_raw.wav", assembled, sample_rate)
        _finish_stage(session, stage)

        # --- master: two-pass loudness normalization ----------------------------------
        stage = _start_stage(session, job, "master")
        mastered_wav = settings.cache_dir() / f"job_{job.id}_mastered.wav"
        normalize_loudness(raw_wav, mastered_wav)
        _finish_stage(session, stage)

        # --- export: MP3 with tags + cover -------------------------------------------
        stage = _start_stage(session, job, "export")
        final_path = output_path or (settings.output_dir() / f"{_safe_filename(book.title)}.mp3")
        cover_path = Path(book.cover_path) if book.cover_path else None
        encode_mp3(mastered_wav, final_path, title=book.title, artist=book.author, album=book.title, cover_path=cover_path)
        _finish_stage(session, stage)

        job.status = JobStatus.done
        job.finished_at = time_now()
        session.add(job)
        session.commit()
        return final_path

    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)
        job.finished_at = time_now()
        session.add(job)
        session.commit()
        raise
