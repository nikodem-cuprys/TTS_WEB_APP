"""Job creation, live progress (SSE), cancellation, and download. A render runs in a
background thread (not the request handler — it can take minutes) with its own DB
session (db.new_session(): the request-scoped session closes once this endpoint
returns). See PLAN.md 'pipeline/runner.py'.
"""
import asyncio
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session
from sse_starlette.sse import EventSourceResponse

from .. import settings_store
from ..db import get_session, new_session
from ..models import Book, Job, JobStatus
from ..pipeline.runner import create_job, run_job
from ..tts.registry import UnsupportedLanguageError, VoiceNotFoundError, engine_for_language, resolve_voice
from ..util import utc_iso

router = APIRouter()

_TERMINAL_STATUSES = (JobStatus.done, JobStatus.failed, JobStatus.cancelled)
_POLL_INTERVAL_S = 0.5


class CreateJobRequest(BaseModel):
    voice: str
    speed: float = 1.0


class JobStageOut(BaseModel):
    name: str
    status: str
    progress: float


class JobOut(BaseModel):
    id: int
    book_id: int
    status: str
    voice: str
    speed: float
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    stages: list[JobStageOut]


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id, book_id=job.book_id, status=job.status, voice=job.voice, speed=job.speed,
        error=job.error, created_at=utc_iso(job.created_at),
        started_at=utc_iso(job.started_at),
        finished_at=utc_iso(job.finished_at),
        stages=[
            JobStageOut(name=s.name, status=s.status, progress=s.progress)
            for s in sorted(job.stages, key=lambda s: s.id or 0)
        ],
    )


def _run_in_background(job_id: int, workers: int, loudness_i: float, loudness_tp: float, loudness_lra: float) -> None:
    with new_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        try:
            run_job(
                session, job, workers=workers,
                loudness_target_i=loudness_i, loudness_target_tp=loudness_tp, loudness_target_lra=loudness_lra,
            )
        except Exception:
            pass  # run_job() already recorded the failure/cancellation on the job row


@router.post("/books/{book_id}/jobs", response_model=JobOut, status_code=201)
def create_render_job(book_id: int, body: CreateJobRequest, session: Session = Depends(get_session)) -> JobOut:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")

    try:
        engine_for_language(book.language)
    except UnsupportedLanguageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        resolve_voice(body.voice)
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    typed = settings_store.get_typed(session)
    job = create_job(session, book, voice=body.voice, speed=body.speed)

    thread = threading.Thread(
        target=_run_in_background,
        args=(
            job.id, typed["tts_workers"],
            typed["loudness_target_i"], typed["loudness_target_tp"], typed["loudness_target_lra"],
        ),
        daemon=True,
    )
    thread.start()

    return _job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_out(job)


@router.get("/books/{book_id}/jobs", response_model=list[JobOut])
def list_book_jobs(book_id: int, session: Session = Depends(get_session)) -> list[JobOut]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return [_job_out(j) for j in sorted(book.jobs, key=lambda j: j.created_at, reverse=True)]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in (JobStatus.queued, JobStatus.running):
        job.status = JobStatus.cancelled
        session.add(job)
        session.commit()
        session.refresh(job)
    return _job_out(job)


@router.get("/jobs/{job_id}/download")
def download_job(job_id: int, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.done or not job.output_path:
        raise HTTPException(status_code=409, detail="job has not finished successfully")
    path = Path(job.output_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="output file is missing")
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


@router.get("/jobs/{job_id}/stream")
def stream_job(job_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """Same file as /download, but without a `filename` — FileResponse only sets
    Content-Disposition: attachment when one is given, and an <audio> element won't
    show duration/allow seeking against a response the browser thinks it should save
    rather than play inline."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.done or not job.output_path:
        raise HTTPException(status_code=409, detail="job has not finished successfully")
    path = Path(job.output_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="output file is missing")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int):
    async def event_generator():
        last_payload: str | None = None
        while True:
            with new_session() as session:
                job = session.get(Job, job_id)
                if job is None:
                    yield {"event": "error", "data": "job not found"}
                    return
                payload = _job_out(job).model_dump_json()
                status = job.status

            if payload != last_payload:
                yield {"event": "update", "data": payload}
                last_payload = payload
            if status in _TERMINAL_STATUSES:
                return
            await asyncio.sleep(_POLL_INTERVAL_S)

    return EventSourceResponse(event_generator())
