"""SQLModel schema. See PLAN.md for the pipeline these tables back."""
from datetime import datetime, timezone
from enum import StrEnum

from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BlockKind(StrEnum):
    heading = "heading"
    para = "para"
    quote = "quote"
    verse = "verse"
    skip = "skip"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class Book(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    author: str | None = None
    language: str = "en"  # ISO 639-1: en, pl, de, zh
    cover_path: str | None = None
    source_path: str  # original uploaded file, under data/books/
    source_format: str  # epub, pdf, txt, docx, ...
    created_at: datetime = Field(default_factory=_utcnow)

    chapters: list["Chapter"] = Relationship(back_populates="book")
    jobs: list["Job"] = Relationship(back_populates="book")
    lexicon_entries: list["LexiconEntry"] = Relationship(back_populates="book")


class Chapter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id")
    index: int  # order within the book
    title: str
    enabled: bool = True

    book: Book = Relationship(back_populates="chapters")
    blocks: list["Block"] = Relationship(back_populates="chapter")


class Block(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id")
    index: int  # order within the chapter
    kind: BlockKind = BlockKind.para
    text: str

    chapter: Chapter = Relationship(back_populates="blocks")


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id")
    status: JobStatus = JobStatus.queued
    voice: str
    engine: str
    speed: float = 1.0
    formats: str = "mp3"  # comma-separated: mp3,m4b,mp4,srt
    video_style: str = "static"  # applies only when "mp4" is in formats: static|waveform|kenburns
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    output_path: str | None = None  # set once "export" finishes; download API reads this

    book: Book = Relationship(back_populates="jobs")
    stages: list["JobStage"] = Relationship(back_populates="job")
    segments: list["Segment"] = Relationship(back_populates="job")
    artifacts: list["JobArtifact"] = Relationship(back_populates="job")


class JobStage(SQLModel, table=True):
    """Coarse progress row per pipeline stage (ingest/normalize/synthesize/assemble/master/export)."""

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    name: str
    status: JobStatus = JobStatus.queued
    progress: float = 0.0  # 0..1
    started_at: datetime | None = None
    finished_at: datetime | None = None

    job: Job = Relationship(back_populates="stages")


class Segment(SQLModel, table=True):
    """One synthesized text chunk: the unit of caching, parallelism, and subtitle timing."""

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    chapter_id: int = Field(foreign_key="chapter.id")
    index: int  # order within the chapter
    text: str
    cache_key: str | None = None  # sha256(text+voice+engine_version+speed+normalizer_version)
    audio_path: str | None = None  # resolved path once synthesized (cache hit or fresh render)
    start_s: float | None = None  # position in the assembled chapter track
    duration_s: float | None = None
    status: JobStatus = JobStatus.queued

    job: Job = Relationship(back_populates="segments")


class JobArtifact(SQLModel, table=True):
    """One exported file produced by a finished job's export stage (mp3/m4b/opus/
    flac/wav/srt/vtt/mp4/chapters) — a job can produce several, one per requested
    format. A format whose track exceeded [M5-8]'s part-duration limit (currently only
    mp4, for YouTube's upload cap) produces several rows sharing that same `format`,
    distinguished by `part_index`/`part_total`; every other format leaves both `None`."""

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    format: str
    path: str
    part_index: int | None = None  # 1-based
    part_total: int | None = None

    job: Job = Relationship(back_populates="artifacts")


class LexiconEntry(SQLModel, table=True):
    """Per-book pronunciation override, applied during normalization."""

    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id")
    pattern: str
    replacement: str
    is_regex: bool = False
    enabled: bool = True

    book: Book = Relationship(back_populates="lexicon_entries")


class Setting(SQLModel, table=True):
    """Single-row-per-key app settings (worker count, loudness target, output dir, ...)."""

    key: str = Field(primary_key=True)
    value: str
