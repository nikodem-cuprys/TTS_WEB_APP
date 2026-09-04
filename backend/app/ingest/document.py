"""The canonical in-memory representation every parser produces and every downstream
pipeline stage (normalize, segment, synthesize) consumes. See PLAN.md 'Architecture'.

Deliberately named Document rather than Book/Chapter/Block to keep the ingest layer
decoupled from the persisted SQLModel tables of the same names in app.models — a
Document is turned into Book/Chapter/Block rows only once, at upload time.
"""
from dataclasses import dataclass, field

from ..models import BlockKind


@dataclass
class DocBlock:
    kind: BlockKind
    text: str


@dataclass
class DocChapter:
    index: int
    title: str
    blocks: list[DocBlock] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Document:
    title: str
    language: str  # ISO 639-1 best guess; may be overridden by the user later
    author: str | None = None
    cover_bytes: bytes | None = None
    cover_mime: str | None = None
    chapters: list[DocChapter] = field(default_factory=list)
