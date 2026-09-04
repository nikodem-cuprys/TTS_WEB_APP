"""Pydantic request/response models for the API. Grows with each milestone's endpoints."""
from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class BlockOut(BaseModel):
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


class BookSummaryOut(BaseModel):
    id: int
    title: str
    author: str | None
    language: str
    source_format: str
    has_cover: bool
    chapter_count: int
    created_at: datetime


class BookDetailOut(BookSummaryOut):
    chapters: list[ChapterSummaryOut]
