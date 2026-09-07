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
from ..audio import loudness
from ..audio.encode import (
    ChapterMarker,
    encode_flac,
    encode_m4b,
    encode_mp3,
    encode_opus,
    encode_wav,
    extract_wav_range,
    write_wav,
)
from ..audio.loudness import normalize_loudness
from ..config import get_settings
from ..models import BlockKind, Book, Chapter, Job, JobArtifact, JobStage, JobStatus, LexiconEntry, Segment
from ..pipeline import cache
from ..publish.chapters_txt import build_youtube_description
from ..publish.split import DEFAULT_PART_LIMIT_S, part_filename, part_title, split_into_parts
from ..publish.subtitles import SubtitleCue, to_srt, to_vtt
from ..text.lexicon import apply_lexicon
from ..text.normalize import get_version as normalizer_version
from ..text.normalize import normalize
from ..text.segment import segment_text
from ..tts.pool import DEFAULT_WORKERS, SynthPool, SynthRequest
from ..tts.registry import engine_for_language
from ..video.cover import generate_cover
from ..video.render import VIDEO_STYLES, render_mp4

STAGE_NAMES = ["prepare", "synthesize", "assemble", "master", "export"]
#: every export format the pipeline knows how to produce — validated against at the
#: API boundary (POST /api/books/{id}/jobs) and looped over in run_job()'s export stage.
SUPPORTED_EXPORT_FORMATS = {"mp3", "m4b", "opus", "flac", "wav", "srt", "vtt", "mp4", "chapters"}
DEFAULT_EXPORT_FORMATS = ["mp3"]
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]+")
#: chunks per pool.synth_many() call in the synthesize stage — small enough that a
#: cancel request is noticed within roughly one batch's worth of synthesis time on a
#: long book, not just between whole stages (which, for "synthesize", the longest
#: stage by far, would otherwise mean waiting for the entire book to finish).
SYNTHESIZE_BATCH_SIZE = 50


class PipelineError(Exception):
    pass


class JobCancelledError(PipelineError):
    pass


@dataclass
class _ChunkPlan:
    chapter_id: int
    text: str
    pause_after_s: float


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name).strip() or "book"


def _build_chunk_plan(chapters: list, language: str, lexicon_entries: list[LexiconEntry]) -> list[_ChunkPlan]:
    """Flattens every enabled chapter's blocks into an ordered chunk plan, deciding
    each chunk's trailing pause from its position: mid-block chunks get the shortest
    (sentence) pause, a block's last chunk gets the paragraph pause unless it's also
    its chapter's last block (chapter pause), and the very last chunk of the book gets
    none. Never crosses a block boundary within one segment_text() call — see
    text/segment.py's docstring on why that matters for this pause logic.

    A `BlockKind.skip` block (e.g. a PDF footnote, [M6-3]) is filtered out before any
    of the above — it's excluded from narration entirely, but stays a real, visible,
    editable block in the UI rather than being silently dropped at parse time."""
    plan: list[_ChunkPlan] = []
    for chapter_i, chapter in enumerate(chapters):
        is_last_chapter = chapter_i == len(chapters) - 1
        blocks = [b for b in sorted(chapter.blocks, key=lambda b: b.index) if b.kind != BlockKind.skip]
        for block_i, block in enumerate(blocks):
            is_last_block = block_i == len(blocks) - 1
            with_lexicon = apply_lexicon(block.text, lexicon_entries)
            normalized = normalize(with_lexicon, language)
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


def _build_chapter_markers(chapters: list[Chapter], segments: list[Segment]) -> list[ChapterMarker]:
    """One marker per enabled chapter that actually produced audio, spanning from its
    first segment's start to the next chapter's start (so the trailing chapter pause
    reads as part of the chapter that precedes it) — or, for the last chapter, to the
    end of the assembled track."""
    by_chapter: dict[int, list[Segment]] = {}
    for segment in segments:
        by_chapter.setdefault(segment.chapter_id, []).append(segment)

    starts = [
        (chapter, min(s.start_s for s in by_chapter[chapter.id]))
        for chapter in chapters
        if chapter.id in by_chapter
    ]

    markers = []
    for i, (chapter, start_s) in enumerate(starts):
        if i + 1 < len(starts):
            end_s = starts[i + 1][1]
        else:
            end_s = max(s.start_s + (s.duration_s or 0.0) for s in by_chapter[chapter.id])
        markers.append(ChapterMarker(start_s=start_s, end_s=end_s, title=chapter.title))
    return markers


def _build_subtitle_cues(segments: list[Segment]) -> list[SubtitleCue]:
    cues = []
    for segment in sorted(segments, key=lambda s: s.index):
        text = segment.text.strip()
        if not text or segment.start_s is None or segment.duration_s is None:
            continue
        cues.append(SubtitleCue(start_s=segment.start_s, end_s=segment.start_s + segment.duration_s, text=text))
    return cues


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


def _set_stage_progress(session: Session, stage: JobStage, progress: float) -> None:
    stage.progress = progress
    session.add(stage)
    session.commit()


def _check_cancelled(session: Session, job: Job) -> None:
    """Re-reads the job's status from the DB — a cancel request comes from a different
    session (the API request that handled POST /api/jobs/{id}/cancel), so only a fresh
    read, not the in-memory `job` object, can see it."""
    session.refresh(job)
    if job.status == JobStatus.cancelled:
        raise JobCancelledError(f"job {job.id} was cancelled")


def create_job(
    session: Session,
    book: Book,
    *,
    voice: str,
    speed: float = 1.0,
    engine_id: str = "kokoro",
    formats: list[str] | None = None,
    video_style: str = "static",
) -> Job:
    job = Job(
        book_id=book.id, status=JobStatus.queued, voice=voice, engine=engine_id, speed=speed,
        formats=",".join(formats or DEFAULT_EXPORT_FORMATS), video_style=video_style,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def run_job(
    session: Session,
    job: Job,
    *,
    workers: int = DEFAULT_WORKERS,
    output_path: Path | None = None,
    loudness_target_i: float = loudness.DEFAULT_TARGET_I,
    loudness_target_tp: float = loudness.DEFAULT_TARGET_TP,
    loudness_target_lra: float = loudness.DEFAULT_TARGET_LRA,
    mp4_part_limit_s: float = DEFAULT_PART_LIMIT_S,
) -> Path:
    settings = get_settings()
    book = session.get(Book, job.book_id)
    if book is None:
        raise PipelineError(f"job {job.id} references a missing book {job.book_id}")

    try:
        # Checked BEFORE flipping to "running": a job cancelled while still queued (or
        # in the brief window before this call) must not have that status clobbered
        # back to running just because run_job() happened to start.
        _check_cancelled(session, job)

        job.status = JobStatus.running
        job.started_at = time_now()
        session.add(job)
        session.commit()

        # --- prepare: normalize + segment + persist Segment rows -------------------
        stage = _start_stage(session, job, "prepare")
        engine = engine_for_language(book.language)
        chapters = sorted([c for c in book.chapters if c.enabled], key=lambda c: c.index)
        if not chapters:
            raise PipelineError(f"book {book.id} has no enabled chapters")

        # apply_lexicon() itself skips disabled entries; no need to filter here too.
        plan = _build_chunk_plan(chapters, book.language, book.lexicon_entries)
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

        # --- synthesize (batched so a cancel request is noticed mid-stage) -----------
        _check_cancelled(session, job)
        stage = _start_stage(session, job, "synthesize")
        results = []
        with SynthPool(workers=workers) as pool:
            for batch_start in range(0, len(requests), SYNTHESIZE_BATCH_SIZE):
                _check_cancelled(session, job)
                batch = requests[batch_start : batch_start + SYNTHESIZE_BATCH_SIZE]
                results.extend(pool.synth_many(batch))
                _set_stage_progress(session, stage, len(results) / len(requests) if requests else 1.0)

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
        _check_cancelled(session, job)
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
        _check_cancelled(session, job)
        stage = _start_stage(session, job, "master")
        mastered_wav = settings.cache_dir() / f"job_{job.id}_mastered.wav"
        normalize_loudness(
            raw_wav, mastered_wav,
            target_i=loudness_target_i, target_tp=loudness_target_tp, target_lra=loudness_target_lra,
        )
        _finish_stage(session, stage)

        # --- export: every requested format, each tagged with title/author/cover ----
        _check_cancelled(session, job)
        stage = _start_stage(session, job, "export")
        base_name = _safe_filename(book.title)
        requested_formats = [f.strip() for f in job.formats.split(",") if f.strip()] or DEFAULT_EXPORT_FORMATS

        cover_path = Path(book.cover_path) if book.cover_path else None
        if cover_path is None and {"mp3", "m4b", "mp4"} & set(requested_formats):
            # [M5-5]: a Pillow-generated fallback, regenerated fresh from the book's
            # current title/author on every render rather than cached on the book row,
            # so an edited title never leaves a stale cover baked into old exports.
            cover_path = generate_cover(
                settings.cache_dir() / f"job_{job.id}_cover.png", title=book.title, author=book.author,
            )

        chapter_markers: list[ChapterMarker] | None = None
        subtitle_cues: list[SubtitleCue] | None = None
        artifact_rows: list[JobArtifact] = []
        primary_path: Path | None = None

        for fmt in requested_formats:
            if fmt == "mp3":
                path = output_path or (settings.output_dir() / f"{base_name}.mp3")
                encode_mp3(
                    mastered_wav, path, title=book.title, artist=book.author, album=book.title,
                    cover_path=cover_path,
                )
            elif fmt == "m4b":
                if chapter_markers is None:
                    chapter_markers = _build_chapter_markers(chapters, segments)
                path = settings.output_dir() / f"{base_name}.m4b"
                encode_m4b(
                    mastered_wav, path, title=book.title, artist=book.author,
                    chapters=chapter_markers, cover_path=cover_path,
                )
            elif fmt == "opus":
                path = settings.output_dir() / f"{base_name}.opus"
                encode_opus(mastered_wav, path, title=book.title, artist=book.author, album=book.title)
            elif fmt == "flac":
                path = settings.output_dir() / f"{base_name}.flac"
                encode_flac(mastered_wav, path, title=book.title, artist=book.author, album=book.title)
            elif fmt == "wav":
                path = settings.output_dir() / f"{base_name}.wav"
                encode_wav(mastered_wav, path, title=book.title, artist=book.author, album=book.title)
            elif fmt == "srt":
                if subtitle_cues is None:
                    subtitle_cues = _build_subtitle_cues(segments)
                path = settings.output_dir() / f"{base_name}.srt"
                path.write_text(to_srt(subtitle_cues), encoding="utf-8")
            elif fmt == "vtt":
                if subtitle_cues is None:
                    subtitle_cues = _build_subtitle_cues(segments)
                path = settings.output_dir() / f"{base_name}.vtt"
                path.write_text(to_vtt(subtitle_cues), encoding="utf-8")
            elif fmt == "mp4":
                # [M5-8]: a book whose track exceeds mp4_part_limit_s (YouTube's 12h cap,
                # by default) is split chapter-aligned into several MP4s instead of one —
                # each its own JobArtifact row sharing format="mp4", distinguished by
                # part_index/part_total. A book under the limit produces exactly the
                # same single, plainly-named file as before this card.
                if chapter_markers is None:
                    chapter_markers = _build_chapter_markers(chapters, segments)
                parts = split_into_parts(chapter_markers, limit_s=mp4_part_limit_s)
                if not parts:
                    # degenerate case: no chapter produced any segments at all (e.g.
                    # every block normalized to empty text) — nothing to split on, so
                    # fall back to a single whole-track file exactly like before this
                    # card, rather than silently producing zero mp4 artifacts.
                    part_path = settings.output_dir() / f"{base_name}.mp4"
                    render_mp4(
                        mastered_wav, part_path, style=job.video_style, cover_path=cover_path,
                        title=book.title, artist=book.author,
                    )
                    artifact_rows.append(JobArtifact(job_id=job.id, format=fmt, path=str(part_path)))
                    if primary_path is None:
                        primary_path = part_path
                    continue
                total_parts = len(parts)
                for part in parts:
                    part_path = settings.output_dir() / part_filename(base_name, "mp4", part.index, total_parts)
                    part_wav = mastered_wav
                    if total_parts > 1:
                        part_wav = settings.cache_dir() / f"job_{job.id}_mp4_part{part.index}.wav"
                        extract_wav_range(mastered_wav, part_wav, part.start_s, part.end_s)
                    render_mp4(
                        part_wav, part_path, style=job.video_style, cover_path=cover_path,
                        title=part_title(book.title, part.index, total_parts), artist=book.author,
                    )
                    artifact_rows.append(
                        JobArtifact(
                            job_id=job.id, format=fmt, path=str(part_path),
                            part_index=part.index if total_parts > 1 else None,
                            part_total=total_parts if total_parts > 1 else None,
                        )
                    )
                    if primary_path is None:
                        primary_path = part_path
                continue
            elif fmt == "chapters":
                if chapter_markers is None:
                    chapter_markers = _build_chapter_markers(chapters, segments)
                path = settings.output_dir() / f"{base_name}.chapters.txt"
                description = build_youtube_description(chapter_markers, title=book.title, author=book.author)
                path.write_text(description, encoding="utf-8")
            else:
                raise PipelineError(f"unsupported export format: {fmt!r}")

            artifact_rows.append(JobArtifact(job_id=job.id, format=fmt, path=str(path)))
            # mp3 stays the "primary" output_path (what the pre-existing /download and
            # /stream endpoints serve) whenever it's requested, for backward
            # compatibility; otherwise the first requested format wins.
            if primary_path is None or fmt == "mp3":
                primary_path = path

        session.add_all(artifact_rows)
        session.commit()
        _finish_stage(session, stage)

        job.status = JobStatus.done
        job.finished_at = time_now()
        job.output_path = str(primary_path)
        session.add(job)
        session.commit()
        return primary_path

    except JobCancelledError:
        job.status = JobStatus.cancelled
        job.finished_at = time_now()
        session.add(job)
        session.commit()
        raise
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)
        job.finished_at = time_now()
        session.add(job)
        session.commit()
        raise
