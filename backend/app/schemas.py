"""Pydantic request/response models for the API. Grows with each milestone's endpoints."""
from datetime import datetime

from pydantic import BaseModel, field_serializer

from .util import utc_iso


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class BlockOut(BaseModel):
    id: int
    index: int
    kind: str
    text: str


class ChapterSummaryOut(BaseModel):
    id: int
    index: int
    title: str
    enabled: bool
    block_count: int


class ChapterDetailOut(BaseModel):
    id: int
    index: int
    title: str
    enabled: bool
    blocks: list[BlockOut]


class ChapterUpdate(BaseModel):
    title: str | None = None
    enabled: bool | None = None


class BlockUpdate(BaseModel):
    text: str


class BookSummaryOut(BaseModel):
    id: int
    title: str
    author: str | None
    language: str
    source_format: str
    has_cover: bool
    chapter_count: int
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, dt: datetime) -> str:
        # See util.utc_iso's docstring: SQLite round-trips this field as naive, which
        # a bare .isoformat() would let JS misread as local time instead of UTC.
        return utc_iso(dt)


class BookDetailOut(BookSummaryOut):
    chapters: list[ChapterSummaryOut]
